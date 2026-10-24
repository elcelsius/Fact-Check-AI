"""Entrada WAV silenciosa no ritmo original, compatível com o fluxo de captura."""

from contextlib import AbstractContextManager
from pathlib import Path
import threading
import time
import wave

from .audio import AudioDevice


def inspect_replay(path):
    path=Path(path).resolve()
    with wave.open(str(path),"rb") as wav:
        rate,channels,frames=wav.getframerate(),wav.getnchannels(),wav.getnframes()
        if wav.getsampwidth()!=2 or not 1<=channels<=32 or not 8000<=rate<=192000 or frames<=0:
            raise ValueError("Escolha um WAV PCM16, de 8 a 192 kHz, com áudio disponível.")
        wav.setpos(frames-1)
        pcm=wav.readframes(1)
        if len(pcm)!=channels*2:
            raise ValueError("O WAV está incompleto. Recupere uma cópia antes do ensaio.")
    stamp=path.stat()
    return {"file_name":path.name,"frames":frames,"sample_rate":rate,"channels":channels,"duration":frames/rate,
            "bytes":stamp.st_size,"mtime_ns":stamp.st_mtime_ns,"paced":True,"audible_playback":False}


def replay_device(path):
    info=inspect_replay(path)
    return AudioDevice(-1,"Ensaio WAV · "+info["file_name"],info["sample_rate"],info["channels"],True)


class WaveBackend:
    """Adapter de entrada; não abre dispositivo nem reproduz som."""
    paInt16,paContinue,paAbort,paInputOverflow=8,0,2,2

    def __init__(self,path,request_stop):
        self.path=Path(path).resolve()
        self.info=inspect_replay(self.path)
        self.request_stop=request_stop

    def PyAudio(self):
        return _WaveAudio(self)


class _WaveAudio(AbstractContextManager):
    def __init__(self,backend):
        self.backend=backend

    def __enter__(self):
        return self

    def __exit__(self,*args):
        return False

    def get_device_info_by_index(self,index):
        return {"isLoopbackDevice":True,"name":"Ensaio WAV · "+self.backend.info["file_name"]}

    def open(self,**options):
        return _WaveStream(self.backend,options["stream_callback"],options["frames_per_buffer"])


class _WaveStream(AbstractContextManager):
    def __init__(self,backend,callback,frames_per_buffer):
        self.backend,self.callback,self.packet=backend,callback,frames_per_buffer
        self.stopped=threading.Event()
        self.worker=None
        self.active=False
        self.error=None

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.stop_stream()

    def start_stream(self):
        self.active=True
        self.worker=threading.Thread(target=self._run,name="wav-replay",daemon=True)
        self.worker.start()

    def is_active(self):
        return self.active

    def stop_stream(self):
        self.stopped.set()
        if self.worker:
            self.worker.join(timeout=5)
        self.active=False

    def _run(self):
        try:
            stamp=self.backend.path.stat()
            if (stamp.st_size,stamp.st_mtime_ns)!=(self.backend.info["bytes"],self.backend.info["mtime_ns"]):
                raise ValueError("O WAV mudou antes do ensaio. Selecione o arquivo novamente.")
            with wave.open(str(self.backend.path),"rb") as wav:
                frames=0
                began=time.perf_counter()
                while pcm:=wav.readframes(self.packet):
                    frames+=len(pcm)//(2*wav.getnchannels())
                    delay=max(0,frames/wav.getframerate()-(time.perf_counter()-began))
                    if self.stopped.wait(delay):
                        return
                    _,status=self.callback(pcm,len(pcm)//(2*wav.getnchannels()),{"input_buffer_adc_time":0},0)
                    if status!=WaveBackend.paContinue:
                        return
                stamp=self.backend.path.stat()
                if frames!=self.backend.info["frames"] or (stamp.st_size,stamp.st_mtime_ns)!=(self.backend.info["bytes"],self.backend.info["mtime_ns"]):
                    raise ValueError("O WAV mudou durante o ensaio. Confira a gravação de origem.")
            if not self.stopped.is_set():
                self.backend.request_stop()
        except Exception as exc:
            self.error=str(exc)
        finally:
            self.active=False
