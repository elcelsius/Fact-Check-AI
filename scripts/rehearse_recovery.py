"""Ensaio destrutivo apenas em um subprocesso próprio e numa sessão descartável.

Sem dispositivo real, modelo ou rede: PCM e registros editoriais são fictícios.
O processo pai mata somente o filho criado aqui; nenhuma sessão real é aberta.
"""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import wave

from factcheck import __version__
from factcheck.audio import AudioDevice
from factcheck.dossiers import DossierStore
from factcheck.exports import snapshot
from factcheck.persistence import atomic_json
from factcheck.recovery import capture_state, inspect_session, playback_path, recover_audio
from factcheck.review import ReviewStore
from factcheck.session import CaptureSession


def seed(folder):
    review = ReviewStore(folder)
    records = [{"paragraph_id": pid, "version": 1, "source_text": f"Fala fictícia {pid}.",
                "text": f"Fala fictícia {pid}.", "start": (pid - 1) * .2, "end": pid * .2,
                "speaker": None, "closed": pid == 1, "parts": []} for pid in (1, 2)]
    with (folder / "paragraphs.jsonl").open("ab") as stream:
        for paragraph in records:
            stream.write((json.dumps(paragraph, ensure_ascii=False) + "\n").encode())
            review.ingest(paragraph)
        stream.write(b'{"paragraph_id": 3, "source_text": "corta\xc3')
    reviewed = review.revise(1, 1, "Fala fictícia conferida para ensaio.", None)
    job, _ = review.begin_analysis(1)
    review.finish_analysis(job, [{"category": "fato", "quote": reviewed["text"], "summary": reviewed["text"],
                          "reason": "Exemplo fictício de recuperação.", "context_notes": []}], {"model": "fixture"})
    dossier = DossierStore(review)
    cid = review.claims()[0]["id"]
    dossier.decide(cid, 0, "inconclusiva", "Revisor fictício", "Ensaio sem dados reais.")
    dossier.begin(cid, "collect")
    review.begin_analysis(1, force=True)
    return {"source": reviewed, "claim_id": cid, "decision": dossier.snapshot(cid)["decision"]}


def child(project):
    class Stream:
        active = False
        def __init__(self, callback):
            self.callback = callback
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.active = False
        def start_stream(self):
            self.active = True
            def feed():
                while self.active:
                    self.callback(b"\x10\x00" * 800, 800, {"input_buffer_adc_time": 0}, 0)
                    time.sleep(.05)
            threading.Thread(target=feed, daemon=True).start()
        def stop_stream(self):
            self.active = False
        def is_active(self):
            return self.active

    class Audio:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get_device_info_by_index(self, index):
            return {"name": "Saída fictícia", "isLoopbackDevice": True}
        def open(self, **kwargs):
            return Stream(kwargs["stream_callback"])

    expected, uncommitted = None, None
    def emit(kind, data):
        nonlocal expected, uncommitted
        if kind == "started":
            expected = seed(Path(data["folder"]))
        if kind == "level" and data["audio_seconds"] >= 2.4 and not uncommitted:
            # Esta alteração deve sumir na recuperação do journal do SQLite.
            uncommitted = sqlite3.connect(session.folder / "review.sqlite3")
            uncommitted.execute("BEGIN IMMEDIATE")
            broken = {**expected["source"], "text": "ALTERAÇÃO NÃO CONFIRMADA"}
            uncommitted.execute("UPDATE paragraphs SET payload=? WHERE id=1", (json.dumps(broken),))
            atomic_json(project / "ready.json", {"folder": str(session.folder), "expected": expected, "pid": os.getpid()})

    session = CaptureSession(AudioDevice(1, "Saída fictícia", 8000, 1), project, emit, transcribe=False)
    module = SimpleNamespace(PyAudio=Audio, paAbort=2, paContinue=0, paInputOverflow=2, paInt16=8)
    with patch.dict("sys.modules", {"pyaudiowpatch": module}):
        session.run()


def rehearse(project):
    project.mkdir(parents=True, exist_ok=True)
    # O python.exe do venv no Windows pode ser um redirecionador com outro PID.
    # Executar o interpretador base com os mesmos caminhos garante um único
    # processo próprio, que pode ser identificado e encerrado com precisão.
    bootstrap = ("import runpy,sys; sys.path[:]= " + repr(sys.path) +
                 "; runpy.run_module('scripts.rehearse_recovery',run_name='__main__')")
    process = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-c", bootstrap, "--child", str(project)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 15
        while not (project / "ready.json").is_file() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(.05)
        if not (project / "ready.json").is_file():
            raise RuntimeError("O subprocesso não ficou pronto para o ensaio.")
        ready = json.loads((project / "ready.json").read_text(encoding="utf8"))
        if ready["pid"] != process.pid:
            raise RuntimeError("A identidade do subprocesso não corresponde ao ensaio.")
        active_before = capture_state(Path(ready["folder"]))[0] == "active"
        process.kill()  # Exclusivamente o filho criado por esta função.
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        _, error = process.communicate(timeout=5)
    if error:
        raise RuntimeError(error)
    folder = Path(ready["folder"])
    originals = {name: (folder / name).read_bytes() for name in ("session.json", "paragraphs.jsonl", "audio.wav")}
    review = ReviewStore(folder)
    warnings = review.import_paragraphs()
    triage = review.recover_interrupted()
    dossier = DossierStore(review)
    research = dossier.recover()
    report = inspect_session(review, warnings)
    expected = ready["expected"]
    checks = {"active_process_detected": active_before, "interrupted_capture_detected": report["state"] == "interrupted",
              "uncommitted_sqlite_change_rolled_back": review.source(1) == expected["source"],
              "human_decision_preserved": dossier.snapshot(expected["claim_id"])["decision"] == expected["decision"],
              "tail_warning": len(warnings) == 1, "interrupted_jobs": triage == research == 1,
              "no_automatic_retry": report["running"] == 0, "audio_present": report["audio"].get("duration", 0) >= 2}
    if report["audio"]["state"] == "repairable":
        recover_audio(review)
    with wave.open(str(playback_path(folder)), "rb") as wav:
        data = wav.readframes(wav.getnframes())
        checks["saved_pcm_preserved"] = data == b"\x10\x00" * (len(data) // 2) and len(data) > 0
    checks["one_unclosed_paragraph"] = len(report["unclosed"]) == 1
    review.close_interrupted_paragraphs(report["unclosed"])
    checks["manual_closure_pending_review"] = review.source(2)["closed"] and not review.source(2)["human_reviewed"]
    checks["original_files_preserved"] = all((folder / name).read_bytes() == value for name, value in originals.items())
    exported = snapshot(review)
    checks["export_after_recovery"] = exported["dossiers"][0]["decision"] == expected["decision"]
    before = review.sources(include_inactive=True)
    repeated_warnings = review.import_paragraphs()
    checks["recovery_is_repeatable"] = (review.sources(include_inactive=True) == before and repeated_warnings == warnings
                                       and review.recover_interrupted() == dossier.recover() == 0)
    if not all(checks.values()):
        raise AssertionError(json.dumps(checks, ensure_ascii=False))
    return {"version": __version__, "synthetic_data": True, "process_kill": True,
            "audio_seconds_available": report["audio"]["duration"], "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    if sys.platform != "win32":
        raise SystemExit("Ensaio destinado ao Windows, incluindo detecção do processo da captura.")
    cache = Path(__file__).resolve().parents[1] / ".cache" / "verification"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="recovery-drill-", dir=cache) as directory:
        report = rehearse(Path(directory))
    atomic_json(cache / "recovery-drill.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
