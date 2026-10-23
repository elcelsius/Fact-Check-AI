"""Janela local de captura e transcrição. Toda alteração visual ocorre na thread Tk."""

import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from . import __version__
from .audio import loopback_devices
from .paragraphs import ParagraphConfig
from .session import CaptureSession
from .workbench import Workbench


def timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


class CaptureApp:
    def __init__(self, root: tk.Tk, project_root: Path, engine_name: str = "streaming",
                 paragraph_pause: float = 1.5):
        self.root = root
        self.project_root = project_root
        self.events: queue.Queue = queue.Queue()
        self.session: CaptureSession | None = None
        self.folder: Path | None = None
        self.closing = False
        self.close_prompt_active = False
        self.activities: dict[str, tuple[str, Callable[[], None]]] = {}
        self.paragraphs: dict[int, dict] = {}
        self.started_at: float | None = None
        self.warning_count = 0
        self.devices = []
        root.title(f"Fact Checking · Falas e afirmações · v{__version__}")
        root.geometry("1120x860")
        root.minsize(1000, 760)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("vista")
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        main = ttk.Frame(root, padding=22)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Captura e transcrição ao vivo", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="Reproduza o vídeo no computador e selecione a saída usada para ouvi-lo.",
                  style="Hint.TLabel").pack(anchor="w", pady=(5, 20))
        event_bar = ttk.Frame(main)
        event_bar.pack(fill="x", pady=(0, 8))
        ttk.Button(event_bar, text="Dados do debate", command=lambda: self.workbench.configure_debate()).pack(side="right")
        ttk.Button(event_bar, text="Configurar IA · API Google", command=lambda: self.workbench.configure_ai()).pack(side="right", padx=8)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)
        main = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(main, text="Captura e transcrição")
        controls = ttk.Frame(main)
        controls.pack(fill="x")
        ttk.Label(controls, text="Saída de áudio").pack(anchor="w")
        device_row = ttk.Frame(controls)
        device_row.pack(fill="x", pady=(5, 10))
        self.device_box = ttk.Combobox(device_row, state="readonly")
        self.device_box.pack(side="left", fill="x", expand=True)
        self.refresh_button = ttk.Button(device_row, text="Atualizar saídas", command=self.refresh)
        self.refresh_button.pack(side="left", padx=(8, 0))
        self.transcribe_enabled = tk.BooleanVar(value=True)
        self.transcribe_check = ttk.Checkbutton(controls, text="Transcrever durante a gravação",
                                               variable=self.transcribe_enabled)
        self.transcribe_check.pack(anchor="w", pady=(0, 8))
        engine_row = ttk.Frame(controls)
        engine_row.pack(fill="x", pady=(0, 12))
        ttk.Label(engine_row, text="Transcrição").pack(side="left", padx=(0, 10))
        self.engine_box = ttk.Combobox(engine_row, state="readonly", width=48,
                                      values=("Contínua · prévia durante a fala", "Whisper · trechos a cada três segundos"))
        self.engine_box.current(0 if engine_name == "streaming" else 1)
        self.engine_box.pack(side="left")
        ttk.Label(engine_row, text="Pausa entre parágrafos (s)").pack(side="left", padx=(16, 6))
        self.paragraph_pause = tk.StringVar(value=f"{paragraph_pause:g}".replace(".", ","))
        self.pause_box = ttk.Spinbox(engine_row, from_=0.8, to=5, increment=0.1,
                                    width=5, textvariable=self.paragraph_pause)
        self.pause_box.pack(side="left")
        action_row = ttk.Frame(main)
        action_row.pack(fill="x")
        self.start_button = ttk.Button(action_row, text="Iniciar captura", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(action_row, text="Encerrar e salvar", command=self.stop,
                                      state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(action_row, text="Cancelar sessão", command=self.cancel,
                                        state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.folder_button = ttk.Button(action_row, text="Abrir pasta da sessão", command=self.open_folder,
                                        state="disabled")
        self.folder_button.pack(side="left")
        self.clock = ttk.Label(action_row, text="00:00:00")
        self.clock.pack(side="right")
        meter_row = ttk.Frame(main)
        meter_row.pack(fill="x", pady=(18, 8))
        ttk.Label(meter_row, text="Nível do áudio").pack(side="left", padx=(0, 12))
        self.meter = ttk.Progressbar(meter_row, maximum=100)
        self.meter.pack(side="left", fill="x", expand=True)
        self.level_label = ttk.Label(meter_row, text="Aguardando", width=26, anchor="e")
        self.level_label.pack(side="right")
        ttk.Label(main, text="Observe o sinal capturado. O volume de escuta pode ficar confortável.",
                  style="Hint.TLabel").pack(anchor="w")
        self.status = ttk.Label(main, text="Pronto para iniciar.")
        self.status.pack(anchor="w", pady=(3, 4))
        self.detail = ttk.Label(main, text="O áudio e o texto serão salvos localmente na pasta recordings.",
                                style="Hint.TLabel", wraplength=900)
        self.detail.pack(anchor="w", pady=(0, 12))
        ttk.Label(main, text="Em andamento · texto provisório, pode mudar", style="Hint.TLabel").pack(anchor="w")
        self.partial = ScrolledText(main, wrap="word", font=("Segoe UI", 12), height=3,
                                    foreground="#555555", background="#F4F6FA", relief="solid",
                                    borderwidth=1, padx=12, pady=8)
        self.partial.pack(fill="x", pady=(6, 12))
        self.partial.configure(state="disabled")
        paragraph_row = ttk.Frame(main)
        paragraph_row.pack(fill="x")
        ttk.Label(paragraph_row, text="Parágrafos · pontuação sugerida · revisão humana pendente",
                  style="Hint.TLabel").pack(side="left")
        self.show_original = tk.BooleanVar(value=False)
        ttk.Checkbutton(paragraph_row, text="Ver texto original", variable=self.show_original,
                        command=self.render_paragraphs).pack(side="right")
        self.transcript = ScrolledText(main, wrap="word", font=("Segoe UI", 12),
                                       height=10, relief="solid", borderwidth=1, padx=12, pady=10)
        self.transcript.pack(fill="both", expand=True, pady=(6, 0))
        self.transcript.configure(state="disabled")
        self.workbench = Workbench(self, self.notebook)
        ttk.Label(event_bar, textvariable=self.workbench.title, wraplength=830).pack(side="left")
        self.refresh()
        self.root.after(100, self.poll)

    def refresh(self) -> None:
        try:
            self.devices = loopback_devices()
            names = [device.name.removesuffix(" [Loopback]") + (" · padrão" if device.is_default else "")
                     for device in self.devices]
            self.device_box["values"] = names
            if self.devices:
                preferred = next((i for i, device in enumerate(self.devices) if device.is_default), 0)
                self.device_box.current(preferred)
                self.start_button.configure(state="normal")
            else:
                self.start_button.configure(state="disabled")
                self.status.configure(text="Nenhuma saída compatível encontrada. Conecte uma saída e atualize.")
        except Exception as exc:
            self.start_button.configure(state="disabled")
            self.status.configure(text="Não foi possível listar as saídas de áudio.")
            self.detail.configure(text=str(exc))

    def start(self) -> None:
        selected = self.device_box.current()
        if self.session or self.closing or not 0 <= selected < len(self.devices):
            return
        if self.workbench.busy():
            messagebox.showinfo("Iniciar captura", "Aguarde ou cancele a triagem e a pesquisa antes de iniciar outra sessão.", parent=self.root)
            return
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except ImportError:
            pass
        try:
            paragraph_config = ParagraphConfig(pause_seconds=float(self.paragraph_pause.get().replace(",", ".")))
        except ValueError:
            messagebox.showerror("Pausa entre parágrafos", "Informe uma pausa entre 0,8 e 5 segundos.", parent=self.root)
            return
        self.paragraphs.clear()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.set_partial("")
        self.warning_count = 0
        self.folder = None
        self.started_at = None
        self.clock.configure(text="00:00:00")
        self.status.configure(text="Preparando sessão…")
        self.detail.configure(text="A primeira preparação do modelo pode exigir download. Aguarde o início da captura.")
        self.start_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.device_box.configure(state="disabled")
        self.transcribe_check.configure(state="disabled")
        self.engine_box.configure(state="disabled")
        self.pause_box.configure(state="disabled")
        self.folder_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.cancel_button.configure(state="normal")
        self.session = CaptureSession(self.devices[selected], self.project_root,
                                       emit=lambda kind, data: self.events.put((kind, data)),
                                       transcribe=self.transcribe_enabled.get(),
                                       engine_name="streaming" if self.engine_box.current() == 0 else "whisper",
                                       paragraph_config=paragraph_config, debate=self.workbench.debate)
        threading.Thread(target=self.session.run, name="capture-session", daemon=True).start()

    def stop(self) -> None:
        if self.session:
            self.session.stop()
            self.started_at = None
            self.stop_button.configure(state="disabled")
            self.status.configure(text="Encerrando e salvando a sessão…")

    def cancel(self) -> None:
        if self.session is None or self.session.cancel_event.is_set():
            return
        confirmed = messagebox.askyesno(
            "Cancelar sessão",
            "Deseja interromper a captura e cancelar as transcrições pendentes?\n\n"
            "Os arquivos já gravados serão mantidos e identificados como uma sessão cancelada.\n"
            "Um trecho em processamento pode levar alguns segundos para encerrar.",
            default=messagebox.NO, icon=messagebox.QUESTION, parent=self.root,
        )
        if not confirmed:
            return
        self._cancel_session()

    def _cancel_session(self) -> None:
        if self.session is None:
            return
        self.session.cancel()
        self.set_partial("")
        self.started_at = None
        self.stop_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.status.configure(text="Cancelando sessão e preservando os arquivos já gravados…")

    def close(self) -> None:
        if self.closing or self.close_prompt_active:
            return
        if not self.session and not self.activities:
            self.root.destroy()
            return
        self.close_prompt_active = True
        try:
            confirmed = messagebox.askyesno(
                "Fechar o aplicativo?",
                "Há uma sessão ou tarefa em andamento.\n\n"
                "Fechar interrompe a gravação e cancela as tarefas pendentes.\n"
                "O texto provisório e os resultados ainda não salvos serão perdidos.\n\n"
                "O áudio e os resultados já gravados serão preservados.\n"
                "Escolha Não para continuar a sessão ou aguardar as tarefas.\n\n"
                "Deseja mesmo fechar?",
                default=messagebox.NO, icon=messagebox.WARNING, parent=self.root,
            )
        finally:
            self.close_prompt_active = False
        if not confirmed:
            return
        self.closing = True
        self.start_button.configure(state="disabled")
        self._cancel_session()
        failures = []
        for _, request_cancel in list(self.activities.values()):
            try:
                request_cancel()
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            self.closing = False
            if self.session is None:
                self.start_button.configure(state="normal" if self.devices else "disabled")
            self.detail.configure(text="Não foi possível interromper uma tarefa. A janela continuará aberta.")
            messagebox.showerror("Fechamento não concluído", "\n".join(failures), parent=self.root)
            return
        self.status.configure(text="Fechando. Aguardando as tarefas pararem e os arquivos serem finalizados…")
        self.finish_close_if_idle()

    def register_activity(self, activity_id: str, label: str,
                          request_cancel: Callable[[], None]) -> None:
        """Registrar na thread Tk antes de iniciar um trabalho, inclusive futuras checagens.

        O worker deve sinalizar o fim por events.put(("activity_done", {"id": ...})),
        somente após persistir seus resultados e liberar os arquivos.
        """
        if self.closing or activity_id in self.activities:
            raise RuntimeError("Não é possível iniciar essa tarefa agora.")
        self.activities[activity_id] = (label, request_cancel)

    def finish_close_if_idle(self) -> bool:
        if self.closing and self.session is None and not self.activities:
            self.root.destroy()
            return True
        return False

    def open_folder(self) -> None:
        if self.folder and self.folder.is_dir():
            os.startfile(str(self.folder))

    def set_partial(self, text: str) -> None:
        self.partial.configure(state="normal")
        self.partial.delete("1.0", "end")
        self.partial.insert("end", text)
        self.partial.see("end")
        self.partial.configure(state="disabled")

    def paragraph_text(self, data: dict) -> str:
        text = data["source_text"] if self.show_original.get() else data["text"]
        speaker = f" · {data['speaker']}" if data.get("speaker") else ""
        return f"[{timestamp(data['start'])} → {timestamp(data['end'])}]{speaker}\n{text}\n\n"

    def update_paragraph(self, data: dict) -> None:
        paragraph_id = data["paragraph_id"]
        existing = self.paragraphs.get(paragraph_id)
        if existing and data["version"] <= existing["version"]:
            return
        previous_last = next(reversed(self.paragraphs), None)
        self.paragraphs[paragraph_id] = data
        if existing and previous_last != paragraph_id:
            self.render_paragraphs()
            return
        self.transcript.configure(state="normal")
        if existing:
            self.transcript.delete("paragraph_tail", "end-1c")
        else:
            self.transcript.mark_set("paragraph_tail", "end-1c")
            self.transcript.mark_gravity("paragraph_tail", "left")
        self.transcript.insert("end-1c", self.paragraph_text(data))
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def render_paragraphs(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        for data in self.paragraphs.values():
            self.transcript.mark_set("paragraph_tail", "end-1c")
            self.transcript.mark_gravity("paragraph_tail", "left")
            self.transcript.insert("end-1c", self.paragraph_text(data))
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def poll(self) -> None:
        for _ in range(200):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status.configure(text=data["text"])
            elif kind == "started":
                self.folder = Path(data["folder"])
                self.workbench.load(self.folder, live=True)
                self.started_at = time.monotonic()
                self.folder_button.configure(state="normal")
                self.status.configure(text=("Capturando. Áudio enviado a cada 0,2 s; a prévia aparece conforme a fala."
                                            if self.engine_box.current() == 0 else
                                            "Capturando. Primeiro envio em dois segundos; depois, a cada três segundos.")
                                      if self.transcribe_enabled.get() else "Capturando e gravando áudio.")
                self.detail.configure(text=f"Sessão: {self.folder.name}")
            elif kind == "level":
                dbfs = data["dbfs"]
                self.meter["value"] = max(0, min(100, (dbfs + 60) / 60 * 100))
                level_text = "Sem sinal" if dbfs < -85 else "Sinal baixo" if dbfs < -45 else "Sinal presente"
                if data["peak"] >= 0.999:
                    level_text = "Perto do limite"
                self.level_label.configure(text=f"{level_text} · {dbfs:.0f} dB")
                if data["queued_chunks"] > (10 if self.engine_box.current() == 0 else 2):
                    self.status.configure(text=f"Capturando. {data['queued_chunks']} trechos aguardando transcrição.")
            elif kind == "partial":
                if not (self.session and self.session.cancel_event.is_set()):
                    self.set_partial(data["text"])
            elif kind == "paragraph":
                if self.session and self.session.cancel_event.is_set():
                    continue
                self.update_paragraph(data)
                self.workbench.on_paragraph(data)
            elif kind == "triage_update":
                self.workbench.triage_update(data)
            elif kind == "research_done":
                self.workbench.evidence.done(data)
            elif kind == "triage_notice":
                self.workbench.last_notice = data["message"]
                self.workbench.progress.configure(text=data["message"])
                self.detail.configure(text=f"Triagem: {data['message']}")
            elif kind == "activity_done":
                self.activities.pop(data["id"], None)
            elif kind == "warning":
                self.warning_count += 1
                self.detail.configure(text=f"Aviso: {data['message']}")
            elif kind == "error":
                self.set_partial("")
                self.detail.configure(text=f"Erro: {data['message']}")
                messagebox.showerror("Captura e transcrição", data["message"], parent=self.root)
            elif kind == "done":
                self.session = None
                self.workbench.refresh()
                self.set_partial("")
                self.started_at = None
                self.meter["value"] = 0
                self.stop_button.configure(state="disabled")
                self.cancel_button.configure(state="disabled")
                self.start_button.configure(state="normal" if self.devices and not self.closing else "disabled")
                self.device_box.configure(state="readonly")
                self.refresh_button.configure(state="normal")
                self.transcribe_check.configure(state="normal")
                self.engine_box.configure(state="readonly")
                self.pause_box.configure(state="normal")
                if data.get("cancelled"):
                    self.status.configure(text="Sessão cancelada. Arquivos já gravados preservados."
                                          if data.get("folder") else "Preparação da sessão cancelada.")
                elif data["success"]:
                    self.status.configure(text=f"Sessão salva. {self.warning_count} aviso(s)." if self.warning_count else "Sessão salva.")
                else:
                    self.status.configure(text="Sessão encerrada. Confira a mensagem acima.")
            if self.finish_close_if_idle():
                return
        if self.started_at is not None:
            self.clock.configure(text=timestamp(time.monotonic() - self.started_at))
        self.root.after(100, self.poll)


def launch(project_root: Path, engine_name: str = "streaming", paragraph_pause: float = 1.5) -> None:
    root = tk.Tk()
    CaptureApp(root, project_root, engine_name=engine_name, paragraph_pause=paragraph_pause)
    root.mainloop()
