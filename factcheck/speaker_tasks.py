"""Análise nativa isolada e cancelável; o processo auxiliar não escreve no banco."""

import multiprocessing as mp
from pathlib import Path
import queue
import threading
import time
import uuid

from .speaker_models import check_cancel, diarize, prepare_models


def _worker(path, root, number, signal, outputs):
    try:
        result=diarize(path,root,number,signal,lambda percent: outputs.put(("progress",percent)))
        outputs.put(("result",result))
    except (ValueError,InterruptedError) as exc:
        outputs.put(("error",str(exc)))
    except Exception:
        outputs.put(("error","Não foi possível analisar o áudio. Confira o formato e os modelos; tente novamente com uma gravação menor."))


class SpeakerTask:
    def __init__(self, root, emit, store=None, num_speakers=0):
        self.root,self.emit,self.store=root,emit,store
        self.token="speakers-"+uuid.uuid4().hex
        self.pending=1
        self.cancelled=threading.Event()
        self.lock=threading.Lock()
        self.process=None
        self.rid,self.audio=store.begin(num_speakers) if store else (None,None)
        self.num_speakers=num_speakers

    def start(self):
        threading.Thread(target=self._run,daemon=True,name="speaker-controller").start()

    def cancel(self):
        with self.lock:
            self.cancelled.set()

    def progress(self,text):
        self.emit("speaker_progress",{"token":self.token,"message":text})

    def _run(self):
        success=False
        signal=None
        message=""
        try:
            check_cancel(self.cancelled)
            if self.store is None:
                prepare_models(self.root,self.cancelled,self.progress)
                check_cancel(self.cancelled)
                message="Modelos preparados e conferidos. A análise de falantes funciona sem API."
            else:
                path=Path(self.store.review.folder)/self.audio["file"]
                context=mp.get_context("spawn")
                outputs,signal=context.Queue(),context.Event()
                self.process=context.Process(target=_worker,args=(str(path),str(self.root),self.num_speakers,signal,outputs),daemon=True)
                self.process.start()
                began=time.monotonic()
                while True:
                    check_cancel(self.cancelled)
                    if time.monotonic()-began>1800:
                        raise ValueError("A análise excedeu trinta minutos. Use uma gravação menor.")
                    try:
                        kind,data=outputs.get(timeout=0.1)
                    except queue.Empty:
                        if not self.process.is_alive():
                            raise ValueError("O processo de falantes foi interrompido; nenhuma atribuição foi aplicada.")
                        continue
                    if kind=="progress":
                        self.progress(f"Separando vozes localmente: {data}% · aguarde a conferência humana.")
                        continue
                    if kind=="error":
                        raise ValueError(data)
                    with self.lock:
                        check_cancel(self.cancelled)
                        accepted=self.store.finish(self.rid,data)
                    message=("Vozes detectadas. Ouça e confira os trechos antes de atribuir participantes." if accepted else
                             "O áudio mudou ou a tarefa deixou de estar ativa. O resultado anterior não foi aplicado.")
                    break
            success=True
        except Exception as exc:
            message=str(exc) if isinstance(exc,(ValueError,InterruptedError)) else "Não foi possível concluir a preparação ou análise dos falantes."
            if self.store:
                self.store.fail(self.rid,message,self.cancelled.is_set())
        finally:
            if signal and self.cancelled.is_set():
                signal.set()
            if self.process:
                self.process.join(0.15)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(2)
            self.pending=0
            self.emit("speaker_done",{"token":self.token,"success":success,"message":message})
