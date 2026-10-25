r"""Comparar motores com o mesmo WAV salvo, sem APIs ou reprodução de som.

.venv\Scripts\python -m scripts.compare_transcription gravação.wav
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from factcheck.benchmarking import PROFILES, compare


def main():
    sys.stdout.reconfigure(encoding="utf8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--profiles", nargs="+", choices=tuple(PROFILES), default=["streaming-cpu", "whisper-cpu"])
    parser.add_argument("--whisper-model", choices=("tiny", "base", "small"), default="small")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or root / ".cache/verification" / ("asr-comparison-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    try:
        report = compare(args.audio, root, output, args.profiles, args.whisper_model, args.repeats,
                         lambda message: print(message, flush=True))
        print(f"Relatório local, com transcrições automáticas: {output.resolve()}")
        return 0 if report["status"] == "completed" else 1
    except KeyboardInterrupt:
        print(f"Ensaio interrompido. Consulte {output.resolve()} e a recuperação da sessão parcial.")
        return 130
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
