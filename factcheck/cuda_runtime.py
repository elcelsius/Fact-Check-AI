"""Bibliotecas opcionais de CUDA 12 da própria venv, sem alterar o Windows."""

import ctypes
import os
from pathlib import Path
import sys


def whisper_cuda_libraries():
    if os.name != "nt":
        return [], []
    vendor = Path(sys.prefix) / "Lib/site-packages/nvidia"
    libraries = [vendor / "cublas/bin/cublas64_12.dll", vendor / "cudnn/bin/cudnn64_9.dll"]
    if any(not path.is_file() for path in libraries):
        raise ValueError("Whisper NVIDIA exige as bibliotecas locais de requirements-gpu.lock. Instale-as na venv ou escolha Whisper em CPU.")
    handles, native = [], []
    try:
        for folder in sorted({path.parent for path in vendor.rglob("*.dll")}):
            handles.append(os.add_dll_directory(str(folder)))
        for path in libraries:
            native.append(ctypes.CDLL(str(path), winmode=0x1100))
    except OSError as exc:
        for handle in handles:
            handle.close()
        raise ValueError("Não foi possível carregar o runtime NVIDIA local; confira requirements-gpu.lock ou escolha CPU.") from exc
    return handles, native
