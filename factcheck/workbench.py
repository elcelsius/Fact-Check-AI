"""Telas de cadastro, revisão e triagem, sem bloquear a captura."""

from dataclasses import asdict
from pathlib import Path
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
import uuid
import wave
import webbrowser

from .review import Debate, ReviewStore, EVENT_KINDS
from .triage import TriageConfig, TriageRunner
from .gemini import MODEL as GEMINI_MODEL
from .evidence_ui import EvidencePane
from .connection_test import ConnectionTest
from .timeline import describe_time, parse_video_position, timestamp, video_range
from .grouping import active, reconciliation_needed
from .exports import ExportTask, FORMATS, SUFFIXES
from .recovery import (AudioRecoveryTask, SAFE_STATES, STATE_NAMES, capture_state,
                       describe, inspect_session, playback_path)
from .queue_filters import (CATEGORIES, LABELS, SCOPES, STATES, QueueFilters, display_state,
                            field_choices, filter_claims, is_current, sort_claims)
from .priorities import FILTERS as PRIORITY_FILTERS, LEVELS, ORDERINGS, PriorityStore, describe_priority, priority_label, priority_payload
from .assignments import AssignmentStore, assignment_label, assignment_payload, describe_assignment
from .library_ui import LibraryPane
from .previous_checks_ui import PreviousChecksPane
from .topics_ui import TopicsPane
from .topics import describe_topic, load_snapshot
from .speakers_ui import SpeakersPane


class Workbench:
    def __init__(self, app, notebook):
        self.app, self.root = app, app.root
        self.store = None
        self.priority_store = None
        self.assignment_store = None
        self.runner = None
        self.connection_test = None
        self.export_task = None
        self.recovery_task = None
        self.import_warnings = []
        self.session_label = tk.StringVar(value="Nenhuma sessão carregada.")
        self.export_label = tk.StringVar(value="Exportação: nenhum arquivo gerado nesta execução.")
        self.connection_handlers = {}
        self.ai_config = TriageConfig()
        self.ai_label = tk.StringVar(value="IA: Local · Qwen3-4B · falas processadas neste computador")
        self.debate = Debate()
        self.video_reference = {"revision": 0, "offset_seconds": None}
        self.timeline_label = tk.StringVar(value="Vídeo: referência não definida · horários relativos à captura.")
        self.sources = {}
        self.claims = {}
        self.visible_claims = {}
        self.case_states = {}
        self.last_notice = ""
        self.title = tk.StringVar(value="Transmissão sem título · participantes não cadastrados")
        self.auto = tk.BooleanVar(value=True)
        self.review_tab = ttk.Frame(notebook, padding=12)
        self.claim_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.review_tab, text="Revisar falas")
        notebook.add(self.claim_tab, text="Afirmações para checagem")
        actions = ttk.Frame(self.review_tab)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Abrir sessão gravada", command=self.open_session).pack(side="left")
        ttk.Button(actions, text="Revisar fala selecionada", command=self.edit_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="Ouvir trecho", command=self.play_selected).pack(side="left")
        ttk.Button(actions, text="Combinar com o próximo", command=self.combine_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="Descombinar", command=self.uncombine_selected).pack(side="left")
        ttk.Button(actions, text="Exportar sessão", command=self.configure_export).pack(side="left", padx=8)
        ttk.Label(self.review_tab, textvariable=self.ai_label, wraplength=950).pack(anchor="w", pady=(0, 8))
        ttk.Label(self.review_tab, textvariable=self.export_label, wraplength=950).pack(anchor="w", pady=(0, 8))
        recovery_row = ttk.Frame(self.review_tab)
        recovery_row.pack(fill="x", pady=(0, 8))
        ttk.Button(recovery_row, text="Estado da sessão", command=self.show_recovery).pack(side="left")
        ttk.Label(recovery_row, textvariable=self.session_label, wraplength=680).pack(side="left", padx=8)
        self.cancel_recovery_button = ttk.Button(recovery_row, text="Cancelar recuperação", command=self.cancel_recovery, state="disabled")
        self.cancel_recovery_button.pack(side="right")
        ttk.Checkbutton(self.review_tab, text="Identificar afirmações automaticamente ao concluir cada parágrafo",
                        variable=self.auto).pack(anchor="w", pady=(0, 8))
        self.source_tree = self.tree(self.review_tab,
            [("time", "Captura (s)", 130), ("video_time", "Vídeo (ref.)", 190),
             ("speaker", "Participante", 140), ("review", "Revisão / triagem", 220), ("text", "Fala", 550)])
        lower = ttk.Frame(self.review_tab)
        lower.pack(fill="x", pady=10)
        ttk.Button(lower, text="Analisar seleção", command=self.analyze_selected).pack(side="left")
        ttk.Button(lower, text="Analisar todos os trechos concluídos", command=self.analyze_all).pack(side="left", padx=8)
        ttk.Button(lower, text="Cancelar triagem", command=self.cancel_triage).pack(side="left")
        ttk.Button(lower, text="Cancelar exportação", command=self.cancel_export).pack(side="left", padx=8)
        self.progress = ttk.Label(self.review_tab, text="Abra uma sessão gravada ou inicie uma captura.", wraplength=950)
        self.progress.pack(anchor="w")
        ttk.Label(self.review_tab, text="A revisão da transcrição e a identificação do participante são manuais. "
                  "A IA sugere afirmações; todas continuam sem verificação factual.", wraplength=950).pack(anchor="w", pady=10)
        ttk.Label(self.claim_tab, text="Aguardando pesquisa significa que ainda não há evidências nem conclusão sobre veracidade.",
                  wraplength=950).pack(side="bottom", anchor="w", pady=8)
        self.build_filters()
        self.claim_tree = self.tree(self.claim_tab,
            [("priority", "Prioridade", 145), ("assignee", "Responsável pelo caso", 170), ("state", "Estado", 180),
             ("category", "Tipo", 90), ("speaker", "Participante", 140), ("text", "Afirmação", 600)], height=6)
        self.claim_tree.bind("<<TreeviewSelect>>", lambda _: self.show_claim())
        row = ttk.Frame(self.claim_tab)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Ouvir fala", command=self.play_claim).pack(side="left")
        ttk.Button(row, text="Revisar origem", command=self.edit_claim_source).pack(side="left", padx=8)
        ttk.Button(row, text="Revisar afirmação", command=self.edit_claim).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Definir prioridade", command=self.edit_priority).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Atribuir responsável", command=self.edit_assignment).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Descartar com justificativa", command=self.discard).pack(side="left")
        ttk.Button(row, text="Abrir dossiê", command=lambda: self.evidence.open_selected()).pack(side="left", padx=8)
        ttk.Button(row, text="Exportar sessão", command=self.configure_export).pack(side="left")
        ttk.Label(self.claim_tab, textvariable=self.export_label, wraplength=950).pack(anchor="w", pady=(0, 8))
        self.claim_detail = ScrolledText(self.claim_tab, wrap="word", height=8, font=("Segoe UI", 11))
        self.claim_detail.pack(fill="both", expand=True)
        self.claim_detail.configure(state="disabled")
        self.evidence = EvidencePane(self, notebook)
        self.library = LibraryPane(self, notebook)
        self.previous_checks = PreviousChecksPane(self, notebook)
        self.topics = TopicsPane(self, notebook)
        self.speakers = SpeakersPane(self, notebook)

    def build_filters(self):
        frame = ttk.LabelFrame(self.claim_tab, text="Filtrar afirmações", padding=8)
        frame.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Buscar").pack(side="left")
        self.claim_query = tk.StringVar()
        ttk.Entry(row, textvariable=self.claim_query).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(row, text="Escopo").pack(side="left")
        self.claim_scope = tk.StringVar(value=SCOPES["all"])
        ttk.Combobox(row, textvariable=self.claim_scope, values=list(SCOPES.values()), state="readonly", width=22).pack(side="left", padx=8)
        ttk.Label(row, text="Ordenar").pack(side="left")
        self.claim_order = tk.StringVar(value=ORDERINGS["recent"])
        ttk.Combobox(row, textvariable=self.claim_order, values=list(ORDERINGS.values()), state="readonly", width=15).pack(side="left", padx=8)
        ttk.Button(row, text="Limpar filtros", command=self.reset_filters).pack(side="right")
        self.filter_options = {
            "category": {"Todos": None, **{label: key for key, label in CATEGORIES.items()}},
            "state": {"Todos": None, **{label: label for label in STATES}},
            "priority": {"Todos": None, **{label: key for key, label in PRIORITY_FILTERS.items()}},
            "speaker": field_choices([], "Não identificado"), "topic": field_choices([], "Sem tema"),
            "assignee": field_choices([], "Sem responsável")}
        self.filter_values, self.filter_boxes = {}, {}
        facets = ttk.Frame(frame)
        facets.pack(fill="x", pady=(5, 0))
        for column, (key, label) in enumerate((("category", "Categoria"), ("state", "Estado"),
                                               ("speaker", "Participante"), ("topic", "Tema"), ("priority", "Prioridade"),
                                               ("assignee", "Responsável"))):
            cell = ttk.Frame(facets, padding=(0, 0, 8 if column < 5 else 0, 0))
            cell.grid(row=0, column=column, sticky="ew")
            facets.columnconfigure(column, weight=2 if key in {"state", "assignee"} else 1)
            ttk.Label(cell, text=label).pack(anchor="w")
            variable = tk.StringVar(value="Todos")
            box = ttk.Combobox(cell, textvariable=variable, values=list(self.filter_options[key]), state="readonly", width=12)
            box.pack(fill="x")
            self.filter_values[key], self.filter_boxes[key] = variable, box
        self.claim_count = tk.StringVar(value="Nenhuma sessão carregada.")
        ttk.Label(self.claim_tab, textvariable=self.claim_count, wraplength=950).pack(anchor="w", pady=(0, 5))
        for variable in (self.claim_query, self.claim_scope, self.claim_order, *self.filter_values.values()):
            variable.trace_add("write", lambda *_: self.apply_filters())

    def reset_filters(self):
        self.claim_query.set("")
        self.claim_scope.set(SCOPES["all"])
        self.claim_order.set(ORDERINGS["recent"])
        for variable in self.filter_values.values():
            variable.set("Todos")

    def apply_filters(self):
        if not hasattr(self, "claim_tree"):
            return
        selected = {key: self.filter_options[key].get(value.get()) for key, value in self.filter_values.items()}
        scope = next((key for key, label in SCOPES.items() if label == self.claim_scope.get()), "all")
        filters = QueueFilters(query=self.claim_query.get(), scope=scope, **selected)
        rows = filter_claims(self.claims.values(), self.sources, self.case_states, filters)
        order = next((key for key, label in ORDERINGS.items() if label == self.claim_order.get()), "recent")
        rows = sort_claims(rows, self.sources, order)
        self.visible_claims = {claim["id"]: claim for claim in rows}
        self._rows(self.claim_tree, {claim["id"]: (priority_label(claim.get("priority")), assignment_label(claim.get("assignment")),
                   display_state(claim, self.sources, self.case_states), CATEGORIES[claim["category"]],
                   claim["speaker"] or "Não identificado", claim["summary"]) for claim in rows})
        current = sum(is_current(claim, self.sources) for claim in self.claims.values())
        self.claim_count.set(f"Exibindo {len(rows)} de {len(self.claims)} itens · {current} atuais · {len(self.claims) - current} históricos/descartados. Filtros afetam a visualização.")
        self.show_claim()

    def update_filter_options(self):
        for key, label in (("speaker", "Não identificado"), ("topic", "Sem tema"), ("assignee", "Sem responsável")):
            selected = self.filter_values[key].get()
            previous = self.filter_options[key].get(selected)
            values = ((claim.get("assignment") or {}).get("name", "") if key == "assignee" else claim.get(key)
                      for claim in self.claims.values())
            options = field_choices(values, label)
            chosen = next((title for title, value in options.items() if value == previous), None)
            if chosen is None:
                chosen = selected
                while chosen in options:
                    chosen += " (sem itens)"
                options[chosen] = previous
            self.filter_options[key] = options
            self.filter_boxes[key].configure(values=list(options))
            if selected != chosen:
                self.filter_values[key].set(chosen)

    @staticmethod
    def tree(parent, columns, height=14):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[item[0] for item in columns], show="headings", height=height, selectmode="browse")
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=60, stretch=key == "text")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def busy(self):
        return (bool(self.runner and self.runner.pending) or self.evidence.busy() or self.speakers.busy()
                or bool(self.connection_test and self.connection_test.pending) or bool(self.export_task and self.export_task.pending)
                or bool(self.recovery_task and self.recovery_task.pending))

    def update_session_status(self):
        if self.store:
            state, _ = capture_state(self.store.folder)
            suffix = " · histórico incompleto; consulte o estado" if self.import_warnings else ""
            self.session_label.set(STATE_NAMES[state] + suffix)

    def show_recovery(self):
        if not self.store:
            messagebox.showinfo("Estado da sessão", "Abra uma sessão gravada ou inicie uma captura.", parent=self.root)
            return
        store = self.store
        report = inspect_session(store, self.import_warnings)
        self.update_session_status()
        window, close = self.dialog("Estado da sessão · retomada e pendências")
        window.geometry("940x730")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        text = ScrolledText(frame, wrap="word", font=("Segoe UI", 11))
        text.pack(fill="both", expand=True, pady=(0, 12))
        text.insert("1.0", describe(report))
        text.configure(state="disabled")
        row = ttk.Frame(frame)
        row.pack(fill="x")

        def require_idle():
            if self.store is not store or self.app.session or self.busy() or capture_state(store.folder)[0] not in SAFE_STATES:
                raise ValueError("Aguarde as tarefas e confirme que a captura terminou antes de recuperar a sessão.")

        def finish_paragraphs():
            try:
                require_idle()
                if not messagebox.askyesno("Encerrar trechos interrompidos",
                        "Usar somente o texto já salvo para encerrar os parágrafos pendentes?\n\n"
                        "O restante da fala pode estar perdido. As correções serão preservadas e a conferência humana continuará pendente.",
                        default=messagebox.NO, parent=window):
                    return
                require_idle()
                count = store.close_interrupted_paragraphs(report["unclosed"])
                self.refresh()
                self.progress.configure(text=f"{count} parágrafo(s) encerrado(s) com texto salvo. Confira o áudio e revise antes da triagem.")
                close()
            except ValueError as exc:
                messagebox.showerror("Encerrar trechos", str(exc), parent=window)

        def repair():
            task = None
            try:
                require_idle()
                task = AudioRecoveryTask(store, lambda kind, data: self.app.events.put((kind, data)))
                self.app.register_activity(task.token, "Recuperação de áudio", task.cancel)
                self.recovery_task = task
                task.start()
                self.cancel_recovery_button.configure(state="normal")
                self.session_label.set("Criando cópia do áudio disponível; original preservado…")
                close()
            except (ValueError, RuntimeError) as exc:
                if task is not None:
                    self.app.activities.pop(task.token, None)
                    self.recovery_task = None
                messagebox.showerror("Recuperar áudio", str(exc), parent=window)

        safe = report["state"] in SAFE_STATES and not self.app.session and not self.busy()
        ttk.Button(row, text="Encerrar parágrafos pendentes", command=finish_paragraphs,
                   state="normal" if safe and report["unclosed"] else "disabled").pack(side="left")
        ttk.Button(row, text="Criar cópia recuperada do áudio", command=repair,
                   state="normal" if safe and report["audio"]["state"] == "repairable" and report["audio"]["frames"]
                   and not report["playable"] else "disabled").pack(side="left", padx=8)
        ttk.Button(row, text="Fechar", command=close).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)

    def cancel_recovery(self):
        task = self.recovery_task
        if task and task.pending and messagebox.askyesno("Cancelar recuperação",
                "Cancelar a criação da cópia recuperada? O áudio original será preservado.", default=messagebox.NO, parent=self.root):
            task.cancel()
            self.session_label.set("Cancelando a recuperação do áudio…")

    def recovery_done(self, data):
        self.app.activities.pop(data["token"], None)
        if self.recovery_task and self.recovery_task.token == data["token"]:
            self.recovery_task = None
            self.cancel_recovery_button.configure(state="disabled")
            self.update_session_status()
            self.progress.configure(text=data["message"])

    def configure_export(self):
        if not self.store:
            messagebox.showinfo("Exportar sessão", "Inicie uma captura ou abra uma sessão gravada.", parent=self.root)
            return
        if self.export_task and self.export_task.pending:
            messagebox.showinfo("Exportar sessão", "Aguarde ou cancele a exportação em andamento.", parent=self.root)
            return
        if self.app.session and self.app.folder != self.store.folder:
            messagebox.showinfo("Exportar sessão", "Aguarde o início da nova captura para exportar seus dados.", parent=self.root)
            return
        store = self.store
        window, close = self.dialog("Exportar sessão e relatório do ensaio")
        window.geometry("850x480")
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Exportar falas, afirmações e fontes", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Formato").pack(anchor="w", pady=(16, 4))
        format_box = ttk.Combobox(frame, state="readonly", values=list(FORMATS.values()))
        format_box.current(0)
        format_box.pack(fill="x")
        include_inactive = tk.BooleanVar(value=False)
        history_box = ttk.Checkbutton(frame, text="Incluir itens substituídos, descartados e desatualizados", variable=include_inactive)
        history_box.pack(anchor="w", pady=16)
        def choose_format(_=None):
            history_box.configure(state="disabled" if list(FORMATS)[format_box.current()].startswith("report_") else "normal")
        format_box.bind("<<ComboboxSelected>>", choose_format)
        ttk.Label(frame, text="JSON reúne os dados e o texto extraído das fontes. Cada CSV contém uma tabela: falas, afirmações ou fontes. "
                  "Os identificadores acompanham os registros para comparação entre exportações.", wraplength=790).pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="A exportação usa os dados salvos no momento da cópia. Falas provisórias e alterações ainda abertas nos editores "
                  "não entram no arquivo. A classificação da IA e a decisão humana permanecem separadas.", wraplength=790).pack(anchor="w")
        ttk.Label(frame, text="Relatório do ensaio (JSON/TXT): resume tempos, filas e pendências. Inclui contagens históricas separadas "
                  "e não mede precisão sem referência humana. Encerre a captura para gerar o relatório.", wraplength=790).pack(anchor="w", pady=(12, 0))

        def save():
            task = None
            try:
                if self.store is not store:
                    raise ValueError("A sessão mudou. Reabra a exportação.")
                kind = list(FORMATS)[format_box.current()]
                if kind.startswith("report_") and self.app.session:
                    raise ValueError("Encerre a captura antes de gerar o relatório do ensaio.")
                include_history = include_inactive.get() and not kind.startswith("report_")
                suffix = SUFFIXES[kind]
                directory = store.folder / "exports"
                directory.mkdir(exist_ok=True)
                filename = filedialog.asksaveasfilename(parent=window, title="Salvar exportação da sessão", initialdir=directory,
                    initialfile=f"sessao-{store.session_id()}-{kind}{'-historico' if include_history else ''}{suffix}",
                    defaultextension=suffix, filetypes=[(suffix[1:].upper(), "*" + suffix)], confirmoverwrite=True)
                if not filename:
                    return
                if self.store is not store:
                    raise ValueError("A sessão mudou. Reabra a exportação.")
                task = ExportTask(store, filename, kind, include_history, lambda event, data: self.app.events.put((event, data)))
                self.app.register_activity(task.token, "Exportação da sessão", task.cancel)
                self.export_task = task
                self.export_label.set("Exportando os registros salvos. A captura e a revisão podem continuar.")
                task.start()
                close()
            except (ValueError, OSError, RuntimeError) as exc:
                if task is not None:
                    self.app.activities.pop(task.token, None)
                    self.export_task = None
                    self.export_label.set("Exportação não iniciada. Confira as informações e tente novamente.")
                messagebox.showerror("Exportar sessão", str(exc), parent=window)

        row = ttk.Frame(frame)
        row.pack(fill="x", side="bottom", pady=(16, 0))
        ttk.Button(row, text="Escolher arquivo e exportar", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=close).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)

    def cancel_export(self):
        task = self.export_task
        if task and task.pending and not task.cancelled.is_set() and messagebox.askyesno(
                "Cancelar exportação", "Cancelar a exportação em andamento? O arquivo só é substituído após a gravação completa.",
                default=messagebox.NO, parent=self.root):
            task.cancel()
            self.export_label.set("Cancelando a exportação…")

    def export_done(self, data):
        self.app.activities.pop(data["token"], None)
        if self.export_task and self.export_task.token == data["token"]:
            self.export_label.set(data["message"])

    def connection_test_done(self, data):
        self.app.activities.pop(data["token"], None)
        handler = self.connection_handlers.pop(data["token"], None)
        if self.connection_test and self.connection_test.token == data["token"]:
            self.connection_test = None
        if handler:
            handler(data)

    def dialog(self, title):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.transient(self.root)
        window.geometry("850x660")
        window.grab_set()
        token = "editor-" + uuid.uuid4().hex
        closed = False

        def close():
            nonlocal closed
            if closed:
                return
            closed = True
            window.destroy()
            self.app.events.put(("activity_done", {"id": token}))

        self.app.register_activity(token, title, close)
        return window, close

    def configure_debate(self):
        if self.app.session or self.busy():
            messagebox.showinfo("Dados da transmissão", "Encerre a captura e aguarde ou cancele as tarefas antes de alterar o cadastro.", parent=self.root)
            return
        window, close = self.dialog("Dados da transmissão")
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        variables = {}
        ttk.Label(frame, text="Tipo de conteúdo").pack(anchor="w")
        kind = ttk.Combobox(frame, state="readonly", values=list(EVENT_KINDS.values()))
        kind.set(EVENT_KINDS[self.debate.event_kind])
        kind.pack(fill="x", pady=4)
        for key, label in [("title", "Nome da transmissão ou do conteúdo"), ("event_date", "Data da fala/transmissão (AAAA-MM-DD)"), ("source_url", "URL do vídeo (opcional)")]:
            ttk.Label(frame, text=label).pack(anchor="w", pady=(8, 4))
            variables[key] = tk.StringVar(value=getattr(self.debate, key))
            ttk.Entry(frame, textvariable=variables[key]).pack(fill="x")
        ttk.Label(frame, text="Em material reexibido, confira a data das declarações e registre o recorte no plano. A data de upload pode ser diferente.",
                  wraplength=790).pack(anchor="w", pady=8)
        ttk.Label(frame, text="Participantes · um nome por linha (opcional)").pack(anchor="w", pady=(12, 4))
        names = ScrolledText(frame, height=8)
        names.pack(fill="both", expand=True)
        names.insert("1.0", "\n".join(self.debate.participants))

        def save():
            try:
                debate = Debate(**{key: value.get().strip() for key, value in variables.items()},
                                participants=names.get("1.0", "end-1c").splitlines(), event_id=self.debate.event_id,
                                event_kind=next(key for key,label in EVENT_KINDS.items() if label==kind.get())).validate()
                if self.store:
                    self.store.save_debate(debate)
                self.debate = debate
                self.update_title()
                self.refresh()
                close()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Dados da transmissão", str(exc), parent=window)

        ttk.Button(frame, text="Salvar cadastro", command=save).pack(side="left", pady=12)
        ttk.Button(frame, text="Cancelar", command=close).pack(side="right", pady=12)
        window.protocol("WM_DELETE_WINDOW", close)

    def configure_timeline(self):
        if self.store is None or (self.app.session and self.app.folder != self.store.folder):
            messagebox.showinfo("Minutagem do vídeo", "Inicie uma captura e aguarde seu início, ou abra uma sessão gravada.", parent=self.root)
            return
        store = self.store
        reference = store.video_reference()
        window, close = self.dialog("Minutagem do vídeo · referência manual")
        window.geometry("760x460")
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Posição do vídeo no início desta captura", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Informe a posição que o vídeo tinha quando a captura começou. "
                  "Você pode preencher durante a gravação ou depois.", wraplength=700).pack(anchor="w", pady=12)
        ttk.Label(frame, text="MM:SS ou HH:MM:SS · deixe vazio para remover a referência").pack(anchor="w", pady=(0, 6))
        value = tk.StringVar(value=timestamp(reference["offset_seconds"]) if reference["offset_seconds"] is not None else "")
        entry = ttk.Entry(frame, textvariable=value, width=25)
        entry.pack(anchor="w")
        entry.focus_set()
        ttk.Label(frame, text="Exemplo: início em 12:30 + trecho aos 30 s da captura = 13:00 no vídeo.",
                  wraplength=700).pack(anchor="w", pady=12)
        ttk.Label(frame, text="A referência é manual e vale somente para esta sessão. "
                  "Se pausar ou saltar no vídeo, inicie outra sessão para manter a correspondência. "
                  "Os horários e o áudio originais são preservados.", wraplength=700).pack(anchor="w", pady=(0, 12))

        def save():
            try:
                if self.store is not store:
                    raise ValueError("A sessão mudou. Reabra a configuração da minutagem.")
                store.save_video_reference(parse_video_position(value.get()), reference["revision"])
                self.refresh()
                close()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Minutagem do vídeo", str(exc), parent=window)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Salvar referência", command=save).pack(side="left")
        ttk.Button(buttons, text="Limpar campo", command=lambda: value.set("")).pack(side="left", padx=8)
        ttk.Button(buttons, text="Cancelar", command=close).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)

    def configure_ai(self):
        if self.app.session or self.busy():
            messagebox.showinfo("Configurar IA", "Encerre a captura e aguarde ou cancele as tarefas antes de mudar o motor.", parent=self.root)
            return
        window, close = self.dialog("Configurar IA · sua chave Google Gemini")
        window.geometry("850x740")
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Motor para identificar afirmações").pack(anchor="w")
        provider = ttk.Combobox(frame, state="readonly", values=["Local · Qwen3-4B", f"Gemini API · {GEMINI_MODEL}"])
        provider.current(0 if self.ai_config.provider == "local" else 1)
        provider.pack(fill="x", pady=(6, 12))
        key_frame = ttk.LabelFrame(frame, text="Sua chave da API Google (Gemini)", padding=12)
        key_frame.pack(fill="x", pady=(0, 12))
        key = tk.StringVar(value=self.ai_config.api_key or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", ""))
        key_row = ttk.Frame(key_frame)
        key_row.pack(fill="x")
        key_entry = ttk.Entry(key_row, textvariable=key, show="*")
        key_entry.pack(side="left", fill="x", expand=True)

        def toggle_key():
            visible = bool(key_entry.cget("show"))
            key_entry.configure(show="" if visible else "*")
            toggle_button.configure(text="Ocultar" if visible else "Mostrar")

        toggle_button = ttk.Button(key_row, text="Mostrar", command=toggle_key)
        toggle_button.pack(side="left", padx=(8, 0))
        ttk.Button(key_row, text="Limpar", command=lambda: key.set("")).pack(side="left", padx=(6, 0))
        ttk.Label(key_frame, text="Cole sua própria chave neste campo. Ela fica somente na memória enquanto o aplicativo estiver aberto.",
                  wraplength=750).pack(anchor="w", pady=(8, 0))
        probe = None
        test_status = tk.StringVar(value="Chave ainda não testada.")
        test_row = ttk.Frame(key_frame)
        test_row.pack(fill="x", pady=(8, 0))
        test_button = ttk.Button(test_row, text="Testar conexão", command=lambda: test_connection())
        test_button.pack(side="left")
        ttk.Label(test_row, text="Faz uma chamada com texto fictício e consome cota; não envia falas.", wraplength=560).pack(side="left", padx=10)
        ttk.Label(key_frame, textvariable=test_status, wraplength=750).pack(anchor="w", pady=(6, 0))

        def changed(*_):
            if probe and probe.pending:
                probe.cancel()
            test_status.set("Chave alterada. Teste novamente se desejar validar a conexão.")

        key.trace_add("write", changed)

        def test_connection():
            nonlocal probe
            if self.app.closing:
                return
            if probe and probe.pending:
                probe.cancel()
                test_status.set("Cancelando teste…")
                return
            try:
                config = TriageConfig("gemini", key.get().strip(), int(rpm.get())).validate()
            except ValueError:
                test_status.set("Informe sua chave e um limite válido de requisições antes de testar.")
                return
            tested_key = key.get()
            probe = ConnectionTest(config, lambda kind, data: self.app.events.put((kind, data)))
            self.connection_test = probe

            def result(data):
                if not window.winfo_exists():
                    return
                test_button.configure(text="Testar conexão")
                test_status.set(data["message"] if key.get() == tested_key else "Chave alterada. Teste novamente para validar a chave atual.")

            self.connection_handlers[probe.token] = result
            self.app.register_activity(probe.token, "Teste de conexão Gemini", probe.cancel)
            test_button.configure(text="Cancelar teste")
            test_status.set("Testando o modelo com texto fictício…")
            probe.start()

        def close_settings():
            if probe and probe.pending:
                probe.cancel()
            if probe:
                self.connection_handlers.pop(probe.token, None)
            close()
        ttk.Label(frame, text="Captura e transcrição continuam locais. Quando Gemini é escolhido, a triagem envia o parágrafo ao Google. "
                  "A análise de evidências envia a fala, o participante informado, a data do debate e trechos das fontes coletadas. "
                  "O áudio permanece local. Na camada gratuita, o Google "
                  "pode usar entradas e respostas para melhorar produtos e permitir revisão humana desses dados.",
                  wraplength=780).pack(anchor="w", pady=8)
        ttk.Label(frame, text="Máximo de requisições por minuto nesta fila").pack(anchor="w", pady=(12, 4))
        rpm = tk.StringVar(value=str(self.ai_config.requests_per_minute))
        ttk.Spinbox(frame, from_=1, to=60, textvariable=rpm, width=8).pack(anchor="w")
        ttk.Label(frame, text="Começamos com 5/minuto. Ajuste conforme as cotas do seu projeto no AI Studio. "
                  "O aplicativo não verifica faturamento: para usar somente a camada gratuita, utilize um projeto sem faturamento "
                  "ativado. Não há troca automática de modelo ou de provedor. Um erro da API interrompe a fila; "
                  "reaplique a configuração para tentar novamente. Limites também podem ser diários ou por tokens.", wraplength=780).pack(anchor="w", pady=12)
        links = ttk.Frame(frame)
        links.pack(fill="x", pady=6)
        ttk.Button(links, text="Criar chave no Google AI Studio", command=lambda: webbrowser.open("https://aistudio.google.com/api-keys")).pack(side="left")
        ttk.Button(links, text="Cotas e limites", command=lambda: webbrowser.open("https://ai.google.dev/gemini-api/docs/rate-limits")).pack(side="left", padx=8)
        ttk.Button(links, text="Tratamento dos dados", command=lambda: webbrowser.open("https://ai.google.dev/gemini-api/terms")).pack(side="left")

        def save():
            try:
                config = TriageConfig("local" if provider.current() == 0 else "gemini", key.get().strip(), int(rpm.get())).validate()
                if self.runner:
                    self.runner.cancel()
                self.runner = None
                self.ai_config = config
                self.ai_label.set("IA: Local · Qwen3-4B · falas processadas neste computador" if config.provider == "local" else
                                  f"IA: Gemini · {GEMINI_MODEL} · texto enviado ao Google · até {config.requests_per_minute} chamadas/min")
                self.progress.configure(text="Configuração aplicada. A próxima análise usará o motor escolhido.")
                close_settings()
            except ValueError:
                messagebox.showerror("Configurar IA", "Confira a chave e o limite de 1 a 60 requisições por minuto.", parent=window)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom", pady=8)
        ttk.Button(buttons, text="Aplicar configuração", command=save).pack(side="left")
        ttk.Button(buttons, text="Cancelar", command=close_settings).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close_settings)

    def update_title(self):
        self.title.set(f"{self.debate.title} · {EVENT_KINDS[self.debate.event_kind]} · {self.debate.event_date} · {len(self.debate.participants)} participante(s)")

    def load(self, folder: Path, live=False):
        if self.busy():
            raise ValueError("Aguarde ou cancele as tarefas antes de abrir outra sessão.")
        if self.runner:
            self.runner.cancel()
        if not live and capture_state(folder)[0] == "active":
            raise ValueError("Esta sessão ainda está sendo capturada ou finalizada por um processo ativo. Aguarde seu encerramento.")
        store = ReviewStore(folder)
        warnings = []
        if not live:
            warnings = store.import_paragraphs()
            store.recover_interrupted()
        self.store = store
        self.priority_store = PriorityStore(store)
        self.assignment_store = AssignmentStore(store)
        self.library.clear_target()
        self.previous_checks.clear_target()
        self.import_warnings = warnings
        self.runner = None
        self.evidence.load(store)
        self.speakers.load(store)
        self.debate = Debate(**store.debate())
        self.update_title()
        self.reset_filters()
        self.refresh()
        self.update_session_status()
        if not live:
            self.progress.configure(text="Sessão carregada. Consulte Estado da sessão para conferir a retomada e as pendências.")

    def open_session(self):
        if self.app.session or self.busy():
            messagebox.showinfo("Abrir sessão", "Encerre a captura e aguarde ou cancele as tarefas atuais.", parent=self.root)
            return
        folder = filedialog.askdirectory(parent=self.root, title="Pasta da sessão gravada", initialdir=self.app.project_root / "recordings")
        if folder:
            try:
                self.load(Path(folder))
                self.app.folder = Path(folder)
                self.app.folder_button.configure(state="normal")
                self.app.paragraphs.clear()
                self.app.render_paragraphs()
                for source in self.store.sources(include_inactive=True):
                    if not source.get("merged_from"):
                        self.app.update_paragraph(source["original"])
                self.progress.configure(text="Sessão carregada. Consulte Estado da sessão para conferir a retomada e as pendências.")
            except Exception as exc:
                messagebox.showerror("Abrir sessão", str(exc), parent=self.root)

    def on_paragraph(self, data):
        if not self.store:
            return
        self.refresh()
        if data["paragraph_id"] not in self.sources:
            return
        if self.auto.get() and data.get("closed") and data.get("end_reason") not in {"cancelamento", "captura_interrompida", "transcricao_interrompida"}:
            self.analyze(data["paragraph_id"])

    def refresh(self):
        if not self.store:
            return
        previous_offset = self.video_reference["offset_seconds"]
        self.video_reference = self.store.video_reference()
        offset = self.video_reference["offset_seconds"]
        self.timeline_label.set("Vídeo: referência não definida · horários relativos à captura." if offset is None else
                                f"Vídeo no início da captura: {timestamp(offset)} · referência manual · revisão {self.video_reference['revision']}")
        if previous_offset != offset:
            self.app.render_paragraphs()
        self.sources = {source["paragraph_id"]: source for source in self.store.sources()}
        priorities = self.priority_store.all()
        assignments = self.assignment_store.all()
        self.claims = {}
        for claim in self.store.claims():
            current = is_current(claim, self.sources)
            self.claims[claim["id"]] = {**claim,
                "priority": priority_payload(claim, priorities.get(claim["id"]), current),
                "assignment": assignment_payload(claim, assignments.get(claim["id"]), current)}
        states = self.store.analysis_states()
        state_names = {"running": "Em análise", "completed": "Triagem pronta", "failed": "Triagem falhou",
                       "cancelled": "Cancelada", "interrupted": "Interrompida", "stale": "Desatualizada"}
        self._rows(self.source_tree, {str(pid): (f"{source['start']:.1f}–{source['end']:.1f}",
            video_range(source, offset) if offset is not None else "Não definida", source["speaker"] or "Não identificado",
            ("Combinado · " if source.get("merged_from") else "")
            + ("Original atualizado" if source["needs_rebase"] else "Conferida" if source["human_reviewed"] else "Pendente")
            + " · " + state_names.get(states.get((pid, source["revision"]), {}).get("status"), "Sem triagem"),
            source["text"][:220]) for pid, source in self.sources.items()})
        self.case_states = self.evidence.store.states() if self.evidence.store else {}
        self.update_filter_options()
        self.apply_filters()
        self.evidence.refresh()
        self.speakers.refresh()

    @staticmethod
    def _rows(tree, rows):
        for key in tree.get_children():
            if key not in rows:
                tree.delete(key)
        for index, (key, values) in enumerate(rows.items()):
            if tree.exists(key):
                tree.item(key, values=values)
            else:
                tree.insert("", "end", iid=key, values=values)
            tree.move(key, "", index)

    def time(self, source):
        return describe_time(source, self.video_reference["offset_seconds"])

    def selected_source(self):
        selected = self.source_tree.selection()
        return self.sources.get(int(selected[0])) if selected else None

    def edit_selected(self):
        source = self.selected_source()
        if source:
            self.edit(source["paragraph_id"])

    def combine_selected(self):
        left = self.selected_source()
        if not left:
            return
        sources = list(self.sources.values())
        index = next(index for index, source in enumerate(sources) if source["paragraph_id"] == left["paragraph_id"])
        if index + 1 >= len(sources):
            messagebox.showinfo("Combinar parágrafos", "Selecione um parágrafo que tenha outro logo abaixo.", parent=self.root)
            return
        right = sources[index + 1]
        if not all(source["closed"] and not source["needs_rebase"] for source in (left, right)):
            messagebox.showinfo("Combinar parágrafos", "Aguarde a conclusão dos dois parágrafos e confira atualizações pendentes da origem.", parent=self.root)
            return
        if left["speaker"] and right["speaker"] and left["speaker"] != right["speaker"]:
            messagebox.showinfo("Combinar parágrafos", "Não é possível combinar falas de participantes diferentes.", parent=self.root)
            return
        store = self.store
        window, close = self.dialog("Combinar parágrafos · conferir contexto")
        window.geometry("850x540")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Confira se os trechos formam uma fala da mesma pessoa.", wraplength=800).pack(anchor="w", pady=(0, 8))
        for source in (left, right):
            ttk.Label(frame, text=f"Trecho {source['paragraph_id']} · {self.time(source)} · {source['speaker'] or 'Não identificado'}",
                      wraplength=800).pack(anchor="w")
        preview = ScrolledText(frame, height=10, wrap="word")
        preview.pack(fill="both", expand=True, pady=12)
        preview.insert("1.0", left["text"].strip() + " " + right["text"].strip())
        preview.configure(state="disabled")
        confirmed = tk.BooleanVar(value=False)
        if not left["speaker"] or not right["speaker"]:
            ttk.Checkbutton(frame, text="Conferi que os dois trechos pertencem à mesma pessoa", variable=confirmed).pack(anchor="w")
        ttk.Label(frame, text="Os originais e o histórico serão preservados. As análises anteriores ficarão desatualizadas. "
                  "O combinado precisará de nova revisão e triagem.", wraplength=800).pack(anchor="w", pady=12)

        def save():
            try:
                if self.store is not store:
                    raise ValueError("A sessão mudou. Reabra a combinação.")
                combined = store.combine(left["paragraph_id"], left["revision"], right["paragraph_id"], right["revision"], confirmed.get())
                self.refresh()
                self.source_tree.selection_set(str(combined["paragraph_id"]))
                self.source_tree.see(str(combined["paragraph_id"]))
                self.progress.configure(text="Parágrafos combinados. Confira a fala e use Analisar seleção para uma nova triagem.")
                close()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Combinar parágrafos", str(exc), parent=window)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Button(row, text="Combinar trechos", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=close).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)

    def uncombine_selected(self):
        source = self.selected_source()
        if not source:
            return
        if not source.get("merged_from"):
            messagebox.showinfo("Descombinar", "Selecione um parágrafo combinado.", parent=self.root)
            return
        store = self.store

        def restore(texts=None, confirmed=False):
            if self.store is not store:
                raise ValueError("A sessão mudou. Reabra a separação dos trechos.")
            restored = store.uncombine(source["paragraph_id"], source["revision"], texts, confirmed)
            self.refresh()
            self.source_tree.selection_set(str(restored[0]["paragraph_id"]))
            self.source_tree.see(str(restored[0]["paragraph_id"]))
            self.progress.configure(text="Parágrafos separados. As análises anteriores continuam no histórico; confira as falas antes de analisar novamente.")

        if not reconciliation_needed(source):
            try:
                restore()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Descombinar", str(exc), parent=self.root)
            return
        window, close = self.dialog("Descombinar · preservar alterações")
        window.geometry("900x760")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="O combinado mudou. Confira a distribuição antes de separar.", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Texto combinado atual · as correções devem ser preservadas integralmente nos dois campos abaixo.", wraplength=850).pack(anchor="w", pady=(10, 4))
        current = ScrolledText(frame, height=4, wrap="word")
        current.pack(fill="both", expand=True)
        current.insert("1.0", source["text"])
        current.configure(state="disabled")
        editors = []
        for pid in source["merged_from"]:
            child = store.source(pid)
            ttk.Label(frame, text=f"Trecho {pid} · {self.time(child)} · {child['speaker'] or 'Não identificado'}", wraplength=850).pack(anchor="w", pady=(10, 4))
            editor = ScrolledText(frame, height=5, wrap="word")
            editor.pack(fill="both", expand=True)
            editor.insert("1.0", child["text"])
            editors.append(editor)
        confirmed = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Conferi a distribuição das alterações e dos trechos atualizados", variable=confirmed).pack(anchor="w", pady=10)
        ttk.Label(frame, text="Os originais e o combinado permanecerão no histórico. Os textos restaurados precisarão de revisão. "
                  "Se o participante foi alterado no combinado, ele será atribuído aos dois trechos. "
                  "Quando a origem tiver mudado, confira também as versões atuais nos campos acima.", wraplength=850).pack(anchor="w", pady=(0, 10))

        def save():
            try:
                restore([editor.get("1.0", "end-1c") for editor in editors], confirmed.get())
                close()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Descombinar", str(exc), parent=window)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Button(row, text="Descombinar preservando texto", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=close).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)

    def edit(self, pid):
        source = self.store.source(pid)
        if not active(source):
            messagebox.showinfo("Revisar fala", "O trecho foi substituído por uma combinação. Selecione o parágrafo ativo em Revisar falas.", parent=self.root)
            return
        if source.get("merged_from") and source["needs_rebase"]:
            messagebox.showinfo("Revisar fala", "A origem do combinado mudou. Use Descombinar para conferir as falas atualizadas.", parent=self.root)
            return
        window, close = self.dialog("Revisar fala · revisão da transcrição")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Trecho {pid} · {self.time(source)} · revisão {source['revision']}").pack(anchor="w")
        if source.get("merged_from"):
            ttk.Label(frame, text="Parágrafos de origem: " + ", ".join(map(str, source["original"]["source_paragraph_ids"]))).pack(anchor="w")
        ttk.Label(frame, text="Original reconhecido · preservado no histórico").pack(anchor="w", pady=(12, 4))
        original = ScrolledText(frame, height=6, wrap="word")
        original.pack(fill="both", expand=True)
        original.insert("1.0", source["original"]["source_text"])
        original.configure(state="disabled")
        ttk.Label(frame, text="Texto corrigido").pack(anchor="w", pady=(12, 4))
        editor = ScrolledText(frame, height=7, wrap="word")
        editor.pack(fill="both", expand=True)
        editor.insert("1.0", source["text"])
        speaker = ttk.Combobox(frame, state="readonly", values=["Não identificado", *self.debate.participants])
        speaker.set(source["speaker"] or "Não identificado")
        speaker.pack(fill="x", pady=8)
        confirmed = tk.BooleanVar(value=source["human_reviewed"])
        ttk.Checkbutton(frame, text="Conferi a transcrição e a atribuição do participante", variable=confirmed).pack(anchor="w")
        ttk.Label(frame, text="Salvar uma alteração torna as análises anteriores desatualizadas.").pack(anchor="w", pady=8)

        def save():
            try:
                self.store.revise(pid, source["revision"], editor.get("1.0", "end-1c"),
                    None if speaker.get() == "Não identificado" else speaker.get(), confirmed.get())
                self.refresh()
                close()
            except ValueError as exc:
                messagebox.showerror("Revisar fala", str(exc), parent=window)

        ttk.Button(frame, text="Salvar revisão", command=save).pack(side="left")
        ttk.Button(frame, text="Ouvir original", command=lambda: self.play(source)).pack(side="left", padx=8)
        ttk.Button(frame, text="Cancelar", command=close).pack(side="right")
        def confirm_close():
            changed = editor.get("1.0", "end-1c") != source["text"] or speaker.get() != (source["speaker"] or "Não identificado") or confirmed.get() != source["human_reviewed"]
            if not changed or messagebox.askyesno("Descartar revisão?", "As alterações ainda não foram salvas. Deseja descartá-las?", default=messagebox.NO, parent=window):
                close()
        window.protocol("WM_DELETE_WINDOW", confirm_close)

    def analyze(self, pid, force=False):
        if not self.store or self.app.closing:
            return
        try:
            if self.runner is None or self.runner.cancelled.is_set():
                if self.runner and self.runner.pending:
                    raise ValueError("Aguarde o cancelamento da triagem anterior.")
                self.runner = TriageRunner(self.app.project_root, self.store, lambda kind, data: self.app.events.put((kind, data)), config=self.ai_config)
            if self.runner.enqueue(pid, force):
                self.last_notice = ""
                if self.runner.token not in self.app.activities:
                    self.app.register_activity(self.runner.token, "Triagem de afirmações", self.runner.cancel)
                self.progress.configure(text=self.queue_status())
                self.refresh()
        except (ValueError, RuntimeError) as exc:
            self.progress.configure(text=str(exc))

    def analyze_selected(self):
        source = self.selected_source()
        if source:
            self.analyze(source["paragraph_id"], force=True)

    def analyze_all(self):
        for pid, source in self.sources.items():
            if source["closed"] and not source["needs_rebase"]:
                self.analyze(pid)

    def cancel_triage(self):
        if self.runner and self.runner.pending and messagebox.askyesno("Cancelar triagem", "Cancelar as análises pendentes? As falas e os resultados já salvos serão preservados.",
                                            default=messagebox.NO, parent=self.root):
            self.runner.cancel()

    def triage_update(self, data):
        if not self.runner or data["token"] != self.runner.token:
            self.app.activities.pop(data["token"], None)
            return
        self.refresh()
        if self.runner.pending:
            self.progress.configure(text=self.queue_status())
        else:
            self.app.activities.pop(self.runner.token, None)
            self.progress.configure(text="Triagem encerrada. " + (self.last_notice or "Confira os itens na aba Afirmações para checagem."))

    def queue_status(self):
        provider = "Gemini" if self.ai_config.provider == "gemini" else "Local"
        return f"Identificando afirmações · {provider}. {self.runner.pending} trecho(s) na fila."

    def selected_claim(self):
        selected = self.claim_tree.selection()
        return self.visible_claims.get(selected[0]) if selected else None

    def edit_claim(self):
        claim = self.selected_claim()
        if not claim:
            return
        source = self.store.source(claim["paragraph_id"])
        if (claim.get("source_outdated") or claim["status"] in {"descartada", "analise_desatualizada"}
                or source["needs_rebase"] or not active(source) or claim["revision"] != source["revision"]):
            messagebox.showinfo("Revisar afirmação", "Selecione uma afirmação da revisão atual e não descartada.", parent=self.root)
            return
        store = self.store
        try:
            vocabulary = load_snapshot(self.app.project_root)
        except ValueError as exc:
            messagebox.showinfo("Revisar afirmação", str(exc), parent=self.root)
            return
        window, close = self.dialog("Revisar afirmação · extração e classificação")
        window.geometry("900x820")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Esta revisão corrige a extração; não valida a transcrição nem conclui sobre a veracidade.", wraplength=850).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="Texto atual da fala · copie um intervalo literal, preservando negações e qualificadores").pack(anchor="w")
        original = ScrolledText(frame, height=4, wrap="word", font=("Segoe UI", 10))
        original.insert("1.0", source["text"])
        original.configure(state="disabled")
        original.pack(fill="both", expand=True, pady=5)
        ttk.Label(frame, text="Citação da afirmação").pack(anchor="w")
        quote = ScrolledText(frame, height=3, wrap="word", font=("Segoe UI", 10))
        quote.insert("1.0", claim["quote"])
        quote.pack(fill="x", pady=5)
        ttk.Label(frame, text="Resumo fiel ao trecho").pack(anchor="w")
        summary = ScrolledText(frame, height=2, wrap="word", font=("Segoe UI", 10))
        summary.insert("1.0", claim["summary"])
        summary.pack(fill="x", pady=5)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="Categoria").pack(side="left")
        category = ttk.Combobox(row, state="readonly", values=list(CATEGORIES.values()), width=18)
        category.set(CATEGORIES[claim["category"]])
        category.pack(side="left", padx=8)
        ttk.Label(row, text="Tema").pack(side="left", padx=(10, 0))
        topic = ttk.Combobox(row, values=sorted((entry["name"] for entry in vocabulary["topics"]), key=str.casefold))
        topic.set(claim.get("topic") or "")
        topic.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(frame, text="Escolha um tema cadastrado ou escreva um tema livre. Variações conhecidas serão padronizadas; "
                  "outros termos ficam visíveis como fora do vocabulário.", wraplength=850).pack(anchor="w", pady=4)
        ttk.Label(frame, text="Justificativa da revisão da extração").pack(anchor="w")
        reason = ScrolledText(frame, height=3, wrap="word", font=("Segoe UI", 10))
        reason.insert("1.0", claim.get("extraction_review", {}).get("reason", ""))
        reason.pack(fill="x", pady=5)
        ttk.Label(frame, text="Salvar preserva a extração automática e o histórico, invalida análise e decisão dependentes e pede conferir "
                  "o planejamento novamente. Uma nova triagem poderá substituir as extrações atuais, mantendo as versões no histórico.", wraplength=850).pack(anchor="w", pady=8)

        def values():
            return {"quote": quote.get("1.0", "end-1c"), "summary": summary.get("1.0", "end-1c"),
                    "category": next(key for key, label in CATEGORIES.items() if label == category.get()),
                    "topic": topic.get().strip() or None}, reason.get("1.0", "end-1c")
        initial = values()

        def save():
            try:
                if self.store is not store:
                    raise ValueError("A sessão mudou. Reabra a revisão.")
                if load_snapshot(self.app.project_root)["sha256"] != vocabulary["sha256"]:
                    raise ValueError("Os temas mudaram. Reabra a revisão para conferir o vocabulário atual.")
                fields, justification = values()
                store.revise_claim(claim["id"], claim.get("claim_revision", 1), source["revision"], fields, justification, topic_vocabulary=vocabulary)
                self.refresh()
                if self.claim_tree.exists(claim["id"]):
                    self.claim_tree.selection_set(claim["id"])
                self.show_claim()
                self.progress.configure(text="Extração revisada. Confira a pergunta e os recortes do dossiê antes de analisar novamente.")
                close()
            except ValueError as exc:
                messagebox.showerror("Revisar afirmação", str(exc), parent=window)

        def cancel():
            if values() == initial or messagebox.askyesno("Descartar revisão da extração?", "Há alterações ainda não salvas. Deseja descartá-las?",
                                                         default=messagebox.NO, parent=window):
                close()
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Salvar revisão da extração", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def edit_priority(self):
        claim = self.selected_claim()
        if not claim:
            return
        if not is_current(claim, self.sources):
            messagebox.showinfo("Definir prioridade", "Selecione uma afirmação atual e não descartada.", parent=self.root)
            return
        store = self.priority_store
        metadata = claim["priority"]
        window, close = self.dialog("Definir prioridade · organização da revisão")
        window.geometry("760x540")
        window.minsize(700, 500)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        summary = ScrolledText(frame, height=3, wrap="word", font=("Segoe UI", 10))
        summary.insert("1.0", claim["summary"])
        summary.configure(state="disabled")
        summary.pack(fill="x", pady=(0, 12))
        ttk.Label(frame, text="Considere relevância pública, urgência e possibilidade de conferir com fontes. "
                  "Aplique os mesmos critérios a todos os participantes. A decisão factual é separada.", wraplength=650).pack(anchor="w", pady=(0, 12))
        if metadata["needs_review"]:
            ttk.Label(frame, text="A extração mudou. Confira o nível e a justificativa antes de confirmar a prioridade.", wraplength=650).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="Prioridade de revisão").pack(anchor="w")
        level = ttk.Combobox(frame, state="readonly", values=list(LEVELS.values()))
        level.set(LEVELS[metadata["level"]])
        level.pack(fill="x", pady=6)
        ttk.Label(frame, text="Justificativa obrigatória · inclusive para remover a prioridade").pack(anchor="w", pady=(8, 0))
        reason = ScrolledText(frame, height=6, wrap="word", font=("Segoe UI", 10))
        reason.insert("1.0", metadata["reason"])
        reason.pack(fill="both", expand=True, pady=6)
        def value():
            return next(key for key, label in LEVELS.items() if label == level.get()), reason.get("1.0", "end-1c")
        initial = value()
        def save():
            try:
                selected_level, explanation = value()
                store.save(claim["id"], metadata["revision"], claim.get("claim_revision", 1), claim["revision"], selected_level, explanation)
                self.refresh()
                if self.claim_tree.exists(claim["id"]):
                    self.claim_tree.selection_set(claim["id"])
                self.show_claim()
                close()
            except ValueError as exc:
                messagebox.showerror("Definir prioridade", str(exc), parent=window)
        def cancel():
            if value() == initial or messagebox.askyesno("Descartar prioridade?", "Há alterações ainda não salvas. Deseja descartá-las?",
                                                        default=messagebox.NO, parent=window):
                close()
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Salvar prioridade", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def edit_assignment(self):
        claim = self.selected_claim()
        if not claim:
            return
        if not is_current(claim, self.sources):
            messagebox.showinfo("Atribuir responsável", "Selecione uma afirmação atual e não descartada.", parent=self.root)
            return
        store = self.assignment_store
        metadata = claim["assignment"]
        window, close = self.dialog("Atribuir responsável · organização do caso")
        window.geometry("760x540")
        window.minsize(700, 500)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        summary = ScrolledText(frame, height=3, wrap="word", font=("Segoe UI", 10))
        summary.insert("1.0", claim["summary"])
        summary.configure(state="disabled")
        summary.pack(fill="x", pady=(0, 12))
        ttk.Label(frame, text="Atribuição local por nome, para organizar quem acompanha o caso. "
                  "O responsável pela decisão factual é registrado ao concluir a revisão. O histórico pode ser consultado no dossiê.", wraplength=650).pack(anchor="w", pady=(0, 12))
        if metadata["needs_review"]:
            ttk.Label(frame, text="A extração mudou. Confira o responsável e o motivo antes de confirmar o vínculo.",
                      wraplength=650).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="Responsável pelo caso · deixe vazio para retirar a atribuição").pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=6)
        names = sorted({item["assignment"]["name"] for item in self.claims.values() if item["assignment"]["name"]}, key=lambda name: (name.casefold(), name))
        name = ttk.Combobox(row, values=names)
        name.set(metadata["name"])
        name.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Limpar nome", command=lambda: name.set("")).pack(side="right", padx=(8, 0))
        ttk.Label(frame, text="Motivo obrigatório · inclusive para trocar ou retirar o responsável").pack(anchor="w", pady=(8, 0))
        reason = ScrolledText(frame, height=6, wrap="word", font=("Segoe UI", 10))
        reason.insert("1.0", metadata["reason"])
        reason.pack(fill="both", expand=True, pady=6)
        def value():
            return name.get(), reason.get("1.0", "end-1c")
        initial = value()
        def save():
            try:
                assignee, explanation = value()
                store.save(claim["id"], metadata["revision"], claim.get("claim_revision", 1), claim["revision"], assignee, explanation)
                self.refresh()
                if self.claim_tree.exists(claim["id"]):
                    self.claim_tree.selection_set(claim["id"])
                self.show_claim()
                close()
            except ValueError as exc:
                messagebox.showerror("Atribuir responsável", str(exc), parent=window)
        def cancel():
            if value() == initial or messagebox.askyesno("Descartar atribuição?", "Há alterações ainda não salvas. Deseja descartá-las?",
                                                        default=messagebox.NO, parent=window):
                close()
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Salvar atribuição", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def show_claim(self):
        claim = self.selected_claim()
        text = "Selecione uma afirmação para conferir a fala e o contexto."
        if claim:
            engine = claim.get("engine", {})
            provenance = f"{engine.get('name', 'Não informado')} · {engine.get('model', 'Modelo não informado')}"
            usage = engine.get("usage", {}).get("totalTokenCount")
            if usage is not None:
                provenance += f" · {usage} tokens informados pela API"
            fields = "\n".join(f"{label}: {claim.get(key) or 'Não definido'}" for key, label in
                [("topic", "Tema"), ("location", "Local"), ("period", "Período"), ("indicator", "Indicador"), ("comparison", "Comparação")])
            text = (f"{LABELS[claim['status']]} · {CATEGORIES[claim['category']]} · {claim['speaker'] or 'Não identificado'}\n"
                    f"Extração: revisão {claim.get('claim_revision', 1)} · " +
                    ("revisada pelo operador; decisão factual separada\n" if claim.get("extraction_review") else "automática, sem revisão da extração\n") +
                    f"Horário aproximado do parágrafo: {self.time(claim)} · parágrafo {claim['paragraph_id']} · revisão {claim['revision']}\n\n"
                    + ("Parágrafos de origem da combinação: " + ", ".join(map(str, claim["source_paragraph_ids"])) + "\n\n"
                       if len(claim.get("source_paragraph_ids", [])) > 1 else "") +
                    f"{describe_priority(claim.get('priority'))}\n\n"
                    f"{describe_assignment(claim.get('assignment'))}\n\n"
                    f"FALA LITERAL\n{claim['quote']}\n\nRESUMO\n{claim['summary']}\n\n{fields}\n\n"
                    f"ORGANIZAÇÃO POR TEMA\n{describe_topic(claim.get('topic_annotation'))}\n\n"
                    f"CRITÉRIO DA EXTRAÇÃO\n{claim['reason']}\n\n"
                    f"MOTOR DA EXTRAÇÃO AUTOMÁTICA\n{provenance}\n\n"
                    f"VALIDAÇÃO AUTOMÁTICA\n{' '.join(claim.get('validation_notes', [])) or 'Citação localizada no texto.'}\n\n"
                    f"REFERÊNCIAS A ESCLARECER\n{', '.join(claim.get('context_notes', [])) or 'Nenhuma referência marcada por estas regras.'}\n\n"
                    f"CONTEXTO DA VERSÃO ANALISADA\n{claim['context']}")
            if claim.get("automatic_extraction"):
                original = claim["automatic_extraction"]
                text += (f"\n\nEXTRAÇÃO AUTOMÁTICA PRESERVADA\n{CATEGORIES[original['category']]}\n{original['quote']}\n\n"
                         f"CRITÉRIO AUTOMÁTICO ORIGINAL\n{original['reason']}")
        self.claim_detail.configure(state="normal")
        self.claim_detail.delete("1.0", "end")
        self.claim_detail.insert("1.0", text)
        self.claim_detail.configure(state="disabled")

    def edit_claim_source(self):
        claim = self.selected_claim()
        if claim:
            self.edit(claim["paragraph_id"])

    def discard(self):
        claim = self.selected_claim()
        if claim:
            reason = simpledialog.askstring("Descartar afirmação", "Motivo do descarte:", parent=self.root)
            if reason:
                self.store.discard_claim(claim["id"], reason)
                self.refresh()

    def play_selected(self):
        source = self.selected_source()
        if source:
            self.play(source)

    def play_claim(self):
        claim = self.selected_claim()
        if claim:
            self.play(claim)

    def play(self, source):
        if self.app.session:
            messagebox.showinfo("Ouvir trecho", "Encerre a captura antes de ouvir um trecho, para evitar gravar novamente o áudio da revisão.", parent=self.root)
            return
        try:
            import winsound
            with wave.open(str(playback_path(self.store.folder)), "rb") as wav:
                start = max(0, int(source["start"] * wav.getframerate()))
                end = min(wav.getnframes(), int(source["end"] * wav.getframerate()))
                if start >= end:
                    raise ValueError("O trecho não tem áudio disponível.")
                wav.setpos(start)
                data = wav.readframes(end - start)
                params = wav.getparams()
            folder = self.app.project_root / ".cache" / "playback"
            folder.mkdir(parents=True, exist_ok=True)
            clip = folder / "trecho.wav"
            winsound.PlaySound(None, 0)
            with wave.open(str(clip), "wb") as wav:
                wav.setparams(params)
                wav.writeframes(data)
            winsound.PlaySound(str(clip), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (OSError, ValueError, wave.Error, RuntimeError) as exc:
            messagebox.showerror("Ouvir trecho", str(exc), parent=self.root)
