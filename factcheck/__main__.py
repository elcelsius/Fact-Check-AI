import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys

from .audio import loopback_devices
from .paragraphs import ParagraphConfig
from .session import CaptureSession
from .transcription import LocalTranscriber


def main() -> int:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Captura da saída do Windows e transcrição local.")
    parser.add_argument("--list-devices", action="store_true", help="Listar apenas saídas WASAPI loopback.")
    parser.add_argument("--prepare-model", action="store_true", help="Baixar e testar o modelo local.")
    parser.add_argument("--prepare-triage-model", action="store_true", help="Baixar o modelo local de identificação de afirmações.")
    parser.add_argument("--prepare-speaker-models", action="store_true", help="Baixar e verificar os modelos de separação de vozes.")
    parser.add_argument("--engine", choices=("streaming", "whisper"), default="streaming",
                        help="Motor local: contínuo (padrão) ou Whisper em janelas.")
    parser.add_argument("--model", choices=("tiny", "base", "small"), default="small",
                        help="Tamanho do modelo quando --engine whisper.")
    parser.add_argument("--whisper-device", choices=("cpu", "cuda"), default="cpu",
                        help="Processador do Whisper; cuda exige o runtime NVIDIA opcional.")
    parser.add_argument("--device", type=int, help="Índice da saída informado por --list-devices.")
    parser.add_argument("--record-seconds", type=float, help="Gravar por uma duração limitada, sem abrir janela.")
    parser.add_argument("--replay-wav", type=Path, help="Ensaiar um WAV PCM16 silenciosamente, no ritmo original, em nova sessão.")
    parser.add_argument("--no-transcription", action="store_true", help="Salvar somente o áudio.")
    parser.add_argument("--paragraph-pause", type=float, default=1.5,
                        help="Pausa mínima para sugerir novo parágrafo, de 0.8 a 5 segundos.")
    args = parser.parse_args()
    if args.whisper_device == "cuda" and args.engine != "whisper":
        parser.error("Use --whisper-device cuda com --engine whisper.")
    if args.replay_wav is not None and args.record_seconds is not None:
        parser.error("Use --replay-wav ou --record-seconds separadamente.")
    if args.record_seconds is not None and args.record_seconds <= 0:
        parser.error("--record-seconds deve ser positivo.")
    try:
        paragraph_config = ParagraphConfig(pause_seconds=args.paragraph_pause)
    except ValueError as exc:
        parser.error(str(exc))
    project_root = Path(__file__).resolve().parent.parent
    (project_root / "logs").mkdir(exist_ok=True)
    logging.basicConfig(filename=project_root / "logs" / "application.log", encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.prepare_triage_model:
            from .triage import prepare_model
            print(prepare_model(project_root))
            return 0
        if args.prepare_speaker_models:
            from .speaker_models import prepare_models
            print(prepare_models(project_root))
            return 0
        if args.prepare_model:
            from .streaming import StreamingTranscriber
            engine = (StreamingTranscriber(project_root) if args.engine == "streaming" else
                      LocalTranscriber(project_root, args.model, device=args.whisper_device))
            print(engine.prepare())
            return 0
        if args.list_devices:
            print(json.dumps([asdict(device) for device in loopback_devices()], ensure_ascii=False, indent=2))
            return 0
        if args.record_seconds is not None or args.replay_wav is not None:
            if args.replay_wav is not None:
                from .replay import replay_device
                device = replay_device(args.replay_wav)
            else:
                devices = loopback_devices()
                device = next((item for item in devices if item.index == args.device), None) if args.device is not None else next(
                    (item for item in devices if item.is_default), devices[0] if devices else None)
            if device is None:
                raise RuntimeError("Saída não encontrada. Execute --list-devices.")

            def emit(kind, data):
                if kind != "level":
                    print(json.dumps({"kind": kind, **data}, ensure_ascii=False), flush=True)

            session = CaptureSession(device, project_root, emit,
                                     transcribe=not args.no_transcription, model_name=args.model,
                                     engine_name=args.engine, paragraph_config=paragraph_config, replay_path=args.replay_wav,
                                     whisper_device=args.whisper_device)
            try:
                return 0 if session.run(args.record_seconds) else 1
            except KeyboardInterrupt:
                session.stop()
                return 130
        from .ui import launch
        launch(project_root, engine_name=args.engine, paragraph_pause=args.paragraph_pause, whisper_device=args.whisper_device)
        return 0
    except Exception as exc:
        logging.exception("Falha ao iniciar aplicação")
        if sys.stderr is not None:
            print(f"Erro: {exc}", file=sys.stderr)
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Fact Checking", f"Não foi possível iniciar: {exc}\nConsulte logs/application.log.")
            root.destroy()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
