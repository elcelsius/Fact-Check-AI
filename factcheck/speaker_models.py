"""Modelos locais para vozes anônimas. Download explícito e integridade fixada."""

from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import wave


SEGMENTATION = {"id": "197666131", "file": "segmentation.tar.bz2", "size": 6958444,
    "sha256": "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488"}
EMBEDDING = {"id": "198893098", "file": "embedding.onnx", "size": 39593761,
    "sha256": "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b"}
MODEL_HASHES = {"segmentation.onnx": "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079",
                "embedding.onnx": EMBEDDING["sha256"]}
ENGINE = {"name": "sherpa-onnx-offline-diarization", "method_version": 1, "compute": "cpu",
          "segmentation": "pyannote-segmentation-3.0", "embedding": "3dspeaker-eres2net-base",
          "model_hashes": MODEL_HASHES}


def check_cancel(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise InterruptedError("Análise de falantes cancelada.")


def file_hash(path, cancelled=None):
    result = sha256()
    with Path(path).open("rb") as stream:
        while body := stream.read(1024*1024):
            check_cancel(cancelled)
            result.update(body)
    return result.hexdigest()


def model_folder(root):
    return Path(root) / "models" / "offline-speakers"


def verify_models(root, cancelled=None):
    folder = model_folder(root)
    if any(not (folder / name).is_file() or file_hash(folder / name, cancelled) != digest for name, digest in MODEL_HASHES.items()):
        raise ValueError("Prepare os modelos de falantes antes de analisar. Arquivos ausentes ou com integridade diferente da versão esperada.")
    return folder


def _download(asset_id, target, cancelled):
    if os.name != "nt":
        from urllib.request import Request, urlopen
        request = Request("https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/assets/"+asset_id,
                          headers={"Accept": "application/octet-stream", "User-Agent": "Fact-Check-AI"})
        with urlopen(request, timeout=30) as source, target.open("wb") as output:
            while body := source.read(256*1024):
                check_cancel(cancelled)
                output.write(body)
        return
    powershell = shutil.which("pwsh") or str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
    script = Path(__file__).resolve().parent / "assets" / "download_speaker_asset.ps1"
    process = subprocess.Popen([powershell, "-NoProfile", "-NonInteractive", "-File", str(script),
                                "-AssetId", asset_id, "-Destination", str(target)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    began = time.monotonic()
    try:
        while process.poll() is None:
            check_cancel(cancelled)
            if time.monotonic()-began > 180:
                raise ValueError("O download dos modelos excedeu três minutos. Tente novamente quando houver conexão.")
            time.sleep(0.1)
        if process.returncode:
            raise ValueError("Não foi possível baixar os modelos públicos. Confira a conexão e tente preparar novamente.")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def prepare_models(root, cancelled=None, progress=None, fetch=None):
    fetch = fetch or _download
    folder = model_folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    for asset in (SEGMENTATION, EMBEDDING):
        check_cancel(cancelled)
        target = folder / asset["file"]
        if target.is_file() and target.stat().st_size == asset["size"] and file_hash(target, cancelled) == asset["sha256"]:
            continue
        if progress:
            progress("Baixando modelos públicos de falantes; áudio e transcrição permanecem neste computador.")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=folder, prefix=".speaker-download-", suffix=".part", delete=False) as stream:
                temporary = Path(stream.name)
            fetch(asset["id"], temporary, cancelled)
            check_cancel(cancelled)
            if temporary.stat().st_size != asset["size"] or file_hash(temporary, cancelled) != asset["sha256"]:
                raise ValueError("O arquivo baixado não corresponde ao modelo fixado. Nenhum arquivo válido foi substituído.")
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    # Não extrair caminhos do tar: ler somente os dois membros conhecidos e gravar destinos fixos.
    with tarfile.open(folder / SEGMENTATION["file"], "r:bz2") as archive:
        for source, target, limit in (("model.onnx", "segmentation.onnx", 6_000_000), ("LICENSE", "LICENSE-segmentation.txt", 10_000)):
            check_cancel(cancelled)
            member = archive.getmember("sherpa-onnx-pyannote-segmentation-3-0/"+source)
            if not member.isfile() or member.size > limit:
                raise ValueError("Pacote de segmentação inválido.")
            body = archive.extractfile(member).read(limit+1)
            if target in MODEL_HASHES and sha256(body).hexdigest() != MODEL_HASHES[target]:
                raise ValueError("O modelo extraído não corresponde à versão fixada.")
            with tempfile.NamedTemporaryFile(dir=folder, prefix=".speaker-model-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                check_cancel(cancelled)
                os.replace(temporary, folder / target)
            finally:
                temporary.unlink(missing_ok=True)
    return verify_models(root, cancelled)


def read_samples(path, cancelled=None):
    """PCM16 → mono → 16 kHz usando a reamostragem do PyAV, sem tocar no WAV."""
    import av
    import numpy as np
    chunks = []
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    with wave.open(str(path), "rb") as wav:
        rate, channels = wav.getframerate(), wav.getnchannels()
        if wav.getsampwidth() != 2 or not 1 <= channels <= 32 or not 8000 <= rate <= 192000:
            raise ValueError("A análise de falantes exige WAV PCM16, de 8 a 192 kHz.")
        if not 0 < wav.getnframes()/rate <= 3*3600:
            raise ValueError("Analise gravações de até três horas, com áudio disponível.")
        while pcm := wav.readframes(rate):
            check_cancel(cancelled)
            mono = np.frombuffer(pcm, dtype="<i2").reshape(-1, channels).mean(axis=1).astype(np.float32) / 32768
            frame = av.AudioFrame.from_ndarray(mono.reshape(1, -1), format="flt", layout="mono")
            frame.sample_rate = rate
            chunks.extend(output.to_ndarray().reshape(-1).copy() for output in resampler.resample(frame))
        chunks.extend(output.to_ndarray().reshape(-1).copy() for output in resampler.resample(None))
    check_cancel(cancelled)
    return np.concatenate(chunks).astype(np.float32, copy=False)


def diarize(path, root, num_speakers=0, cancelled=None, progress=None):
    import sherpa_onnx as so
    folder = verify_models(root, cancelled)
    if type(num_speakers) is not int or not 0 <= num_speakers <= 30:
        raise ValueError("Informe de zero a trinta vozes; zero estima a quantidade.")
    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(folder/"segmentation.onnx")), num_threads=2, provider="cpu"),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=str(folder/"embedding.onnx"), num_threads=2, provider="cpu"),
        clustering=so.FastClusteringConfig(num_clusters=num_speakers or -1, threshold=0.75), min_duration_on=0.3, min_duration_off=0.5)
    if not config.validate():
        raise ValueError("A configuração dos modelos de falantes é inválida.")
    samples = read_samples(path, cancelled)
    model = so.OfflineSpeakerDiarization(config)
    began = time.monotonic()
    def callback(current, total):
        if progress:
            progress(round(current/max(1,total)*100))
        return int(cancelled is not None and cancelled.is_set())
    result = model.process(samples, callback=callback).sort_by_start_time()
    check_cancel(cancelled)
    segments = [{"start": float(item.start), "end": float(item.end), "voice": int(item.speaker)} for item in result]
    return {"segments": segments, "engine": {**ENGINE, "version": so.__version__, "num_speakers_requested": num_speakers,
            "clustering_threshold": 0.75, "seconds": round(time.monotonic()-began,3)}, "audio_sha256": file_hash(path, cancelled)}
