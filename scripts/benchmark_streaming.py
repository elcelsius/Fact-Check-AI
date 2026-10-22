r"""Ensaio sem captura: alimentar um WAV no ritmo original e medir a entrega.

Executar da raiz: .venv\Scripts\python -m scripts.benchmark_streaming arquivo.wav
"""

import argparse
import json
from pathlib import Path
import sys
import time
import wave

import numpy as np

from factcheck.audio import AudioChunk
from factcheck.streaming import PACKET_SECONDS, StreamingTranscriber


def benchmark(path: Path, root: Path) -> dict:
    engine = StreamingTranscriber(root)
    load_started = time.perf_counter()
    engine.prepare()
    preparation = time.perf_counter() - load_started
    processing, delivery_lags, changes, stabilized = [], [], [], []
    previous = ""
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("O ensaio exige WAV PCM16.")
        rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
        started = time.perf_counter()
        offset = 0
        while pcm := wav.readframes(round(rate * PACKET_SECONDS)):
            chunk = AudioChunk(offset, pcm, rate, channels)
            offset += len(pcm) // (channels * 2)
            time.sleep(max(0, chunk.end - (time.perf_counter() - started)))
            before = time.perf_counter()
            lines = engine.transcribe(chunk)
            now = time.perf_counter()
            processing.append(now - before)
            delivery_lags.append(now - started - chunk.end)
            for line in lines:
                stabilized.append({**line.to_dict(), "delivered_seconds": now - started})
            if engine.partial["text"] != previous:
                if engine.partial["text"]:
                    changes.append({**engine.partial, "audio_supplied_seconds": chunk.end,
                                    "delivered_seconds": now - started})
                previous = engine.partial["text"]
        before = time.perf_counter()
        lines = engine.finish()
        flush_seconds = time.perf_counter() - before
        for line in lines:
            stabilized.append({**line.to_dict(), "delivered_seconds": time.perf_counter() - started})
    return {
        "audio_file": str(path), "audio_duration_seconds": frames / rate,
        "packet_seconds": PACKET_SECONDS, "paced_replay": True,
        "preparation_seconds_excluded_from_latency": preparation,
        "first_partial_seconds": changes[0]["delivered_seconds"] if changes else None,
        "first_partial_text": changes[0]["text"] if changes else None,
        "processing_total_seconds": sum(processing),
        "processing_to_audio_ratio": sum(processing) / (frames / rate),
        "packet_processing_p50_seconds": float(np.percentile(processing, 50)),
        "packet_processing_p95_seconds": float(np.percentile(processing, 95)),
        "packet_delivery_lag_p95_seconds": float(np.percentile(delivery_lags, 95)),
        "flush_seconds": flush_seconds, "partial_updates": changes,
        "stabilized_segments": stabilized,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".cache/verification/streaming-paced.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    results = []
    for path in args.audio:
        result = benchmark(path, root)
        results.append(result)
        print(json.dumps({key: value for key, value in result.items()
                          if key not in {"partial_updates", "stabilized_segments"}}, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
