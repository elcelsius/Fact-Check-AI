"""Coleção compartilhada entre sessões, sem coleta ou validação automática."""

import sqlite3
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .discovery import search_basis
from .queue_filters import field_choices
from .source_library import FIELDS, SourceLibrary, filter_references, render_reference


class LibraryPane:
    def __init__(self, work, notebook):
        self.work, self.root, self.notebook = work, work.root, notebook
        self.store, self.target = None, None
        self.entries, self.visible, self.histories = {}, {}, {}
        self.tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab, text="Coleção de fontes")
        ttk.Label(self.tab, text="Referências de pesquisa reutilizáveis entre sessões. Cadastros e notas são informados pelo operador; "
                  "o conteúdo precisa ser coletado e conferido no dossiê.", wraplength=920).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Buscar").pack(side="left")
        self.query = tk.StringVar()
        ttk.Entry(row, textvariable=self.query).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(row, text="Tema").pack(side="left")
        self.topic = tk.StringVar(value="Todos")
        self.topic_options = field_choices([], "Sem tema")
        self.topic_box = ttk.Combobox(row, textvariable=self.topic, values=list(self.topic_options), state="readonly", width=22)
        self.topic_box.pack(side="left", padx=8)
        self.archived = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Incluir arquivadas", variable=self.archived).pack(side="right")
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Nova referência", command=lambda: self.edit()).pack(side="left")
        self.edit_button = ttk.Button(row, text="Editar referência", command=self.edit_selected, state="disabled")
        self.edit_button.pack(side="left", padx=8)
        self.archive_button = ttk.Button(row, text="Arquivar / restaurar", command=self.archive, state="disabled")
        self.archive_button.pack(side="left")
        ttk.Button(row, text="Atualizar lista", command=self.refresh).pack(side="left", padx=8)
        ttk.Button(row, text="Limpar filtros", command=self.reset_filters).pack(side="right")
        self.count = tk.StringVar(value="A coleção local será carregada ao abrir esta aba.")
        ttk.Label(self.tab, textvariable=self.count).pack(anchor="w", pady=4)
        self.tree = work.tree(self.tab, [("state", "Estado", 90), ("text", "Referência", 380),
                                         ("institution", "Instituição informada", 190), ("topics", "Temas", 220)], height=6)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=8)
        self.use_button = ttk.Button(row, text="Usar URL no dossiê", command=self.use, state="disabled")
        self.use_button.pack(side="left")
        self.target_label = tk.StringVar(value="Sem dossiê de destino. Abra uma afirmação e use Coleção de fontes no dossiê.")
        ttk.Label(row, textvariable=self.target_label, wraplength=690).pack(side="left", padx=12)
        self.status = tk.StringVar(value="A coleção funciona localmente, sem chave de API.")
        ttk.Label(self.tab, textvariable=self.status, wraplength=920).pack(anchor="w", pady=4)
        self.preview = ScrolledText(self.tab, wrap="word", height=8, font=("Segoe UI", 10))
        self.preview.pack(fill="both", expand=True, pady=(4, 0))
        self.preview.configure(state="disabled")
        for variable in (self.query, self.topic, self.archived):
            variable.trace_add("write", lambda *_: self.apply_filters())
        notebook.bind("<<NotebookTabChanged>>", self.tab_changed, add="+")

    def ensure_store(self):
        if self.store is not None:
            return True
        try:
            self.store = SourceLibrary(self.work.app.project_root / "library")
            return True
        except (OSError, sqlite3.Error):
            self.status.set("Não foi possível abrir a coleção local. Confira acesso e espaço na pasta do aplicativo.")
            return False

    def tab_changed(self, _=None):
        if self.notebook.select() == str(self.tab):
            self.refresh()

    def clear_target(self):
        self.target = None
        self.target_label.set("Sem dossiê de destino. Abra uma afirmação e use Coleção de fontes no dossiê.")
        self.use_button.configure(state="disabled")

    def open_for_case(self):
        pane = self.work.evidence
        if not pane.store or not pane.cid or self.work.app.closing:
            return
        snapshot = pane.store.snapshot(pane.cid)
        if not snapshot["valid"]:
            messagebox.showinfo("Coleção de fontes", "Abra uma afirmação atual antes de escolher uma referência.", parent=self.root)
            return
        self.target = {"store": pane.store, "cid": pane.cid, "basis": search_basis(snapshot["claim"], snapshot.get("plan"))}
        self.target_label.set("Destino: " + snapshot["claim"]["summary"][:160])
        self.notebook.select(self.tab)
        self.refresh()

    def refresh(self):
        if not self.ensure_store():
            return
        try:
            self.entries = {entry["id"]: entry for entry in self.store.entries()}
            previous = self.topic_options.get(self.topic.get())
            options = field_choices((topic for entry in self.entries.values() for topic in entry["topics"]), "Sem tema")
            chosen = next((label for label, value in options.items() if value == previous), None)
            if chosen is None:
                chosen = self.topic.get()
                while chosen in options:
                    chosen += " (sem itens)"
                options[chosen] = previous
            self.topic_options = options
            self.topic_box.configure(values=list(options))
            if self.topic.get() != chosen:
                self.topic.set(chosen)
            self.histories = {}
            self.apply_filters()
        except (ValueError, OSError, sqlite3.Error):
            self.status.set("Não foi possível ler a coleção local. Confira a pasta e tente atualizar a lista.")

    def reset_filters(self):
        self.query.set("")
        self.topic.set("Todos")
        self.archived.set(False)

    def apply_filters(self):
        rows = filter_references(self.entries.values(), self.query.get(), self.topic_options.get(self.topic.get()), self.archived.get())
        self.visible = {entry["id"]: entry for entry in rows}
        self.work._rows(self.tree, {entry["id"]: ("Arquivada" if entry["archived"] else "Ativa", entry["title"],
                         entry["institution"], "; ".join(entry["topics"])) for entry in rows})
        self.count.set(f"Exibindo {len(rows)} de {len(self.entries)} referências. Cadastro não equivale a evidência coletada.")
        self.show_selected()

    def selected(self):
        values = self.tree.selection()
        return self.visible.get(values[0]) if values else None

    def show_selected(self):
        entry = self.selected()
        self.edit_button.configure(state="normal" if entry else "disabled")
        self.archive_button.configure(state="normal" if entry else "disabled",
                                      text="Restaurar referência" if entry and entry["archived"] else "Arquivar referência")
        self.use_button.configure(state="normal" if entry and not entry["archived"] and self.target else "disabled")
        text = "Selecione uma referência para conferir os recortes informados e o histórico do cadastro."
        if entry:
            text = render_reference(entry) + "\n\nHISTÓRICO DO CADASTRO\n"
            try:
                if entry["id"] not in self.histories:
                    self.histories[entry["id"]] = self.store.history(entry["id"])
                for change in self.histories[entry["id"]]:
                    kind = {"created": "Cadastro", "edited": "Edição", "archived": "Arquivamento", "restored": "Restauração"}.get(change["kind"], "Alteração")
                    text += (f"\n{change['at']} · {kind} · motivo: {change['current']['change_reason']}\n"
                             + render_reference(change["current"]) + "\n")
            except (ValueError, OSError, sqlite3.Error):
                text += "Histórico indisponível. Atualize a lista."
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def edit_selected(self):
        entry = self.selected()
        if entry:
            self.edit(entry)

    def edit(self, entry=None, prefill=None):
        if not self.ensure_store() or self.work.app.closing:
            return
        if entry is None and prefill:
            entry = next((value for value in self.store.entries() if value["url"] == prefill["url"]), None)
        data = entry or prefill or {key: [] if key == "topics" else "" for key in FIELDS}
        window, close = self.work.dialog("Editar referência da coleção" if entry else "Nova referência da coleção")
        window.geometry("900x760")
        window.minsize(820, 700)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Referência de pesquisa. Salvar não consulta a URL nem confere o documento. "
                  "Campos metodológicos vazios permanecem a definir.", wraplength=770).pack(anchor="w", pady=(0, 8))
        if entry:
            ttk.Label(frame, text=f"Versão {entry['revision']} · " + ("Arquivada; editar não restaura a referência." if entry["archived"] else "Referência ativa."),
                      wraplength=770).pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom", pady=(8, 0))
        reason_frame = ttk.Frame(frame)
        reason_frame.pack(fill="x", side="bottom", pady=(8, 0))
        ttk.Label(reason_frame, text="Motivo obrigatório do cadastro / alteração").pack(anchor="w")
        reason = ScrolledText(reason_frame, height=2, wrap="word")
        reason.pack(fill="x", pady=4)
        reason.insert("1.0", entry["change_reason"] if entry else "")
        tabs = ttk.Notebook(frame)
        tabs.pack(fill="both", expand=True)
        basic, methods = ttk.Frame(tabs, padding=10), ttk.Frame(tabs, padding=10)
        tabs.add(basic, text="Cadastro")
        tabs.add(methods, text="Metodologia e limites")
        fields = {}
        for key, label in (("title", "Título da referência"), ("url", "URL institucional HTTPS"),
                           ("institution", "Instituição informada"), ("topics", "Temas · separados por ponto e vírgula · até oito"),
                           ("periodicity", "Periodicidade informada · se conhecida")):
            ttk.Label(basic, text=label).pack(anchor="w", pady=(5, 0))
            fields[key] = ttk.Entry(basic)
            fields[key].insert(0, "; ".join(data[key]) if key == "topics" else data[key])
            fields[key].pack(fill="x", pady=4)
        for parent, key, label, height in ((basic, "notes", "Observações", 4),
                (methods, "methodology", "Metodologia informada · se conhecida", 6),
                (methods, "limits", "Limites de uso e recortes que precisam de conferência", 6)):
            ttk.Label(parent, text=label).pack(anchor="w", pady=(5, 0))
            fields[key] = ScrolledText(parent, height=height, wrap="word")
            fields[key].insert("1.0", data[key])
            fields[key].pack(fill="both", expand=True, pady=4)
        def value():
            result = {key: widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get() for key, widget in fields.items()}
            result["topics"] = [topic.strip() for topic in result["topics"].split(";") if topic.strip()]
            return result, reason.get("1.0", "end-1c")
        initial = value()
        def save():
            try:
                values, explanation = value()
                saved = self.store.save(values, explanation, entry["id"] if entry else None, entry["revision"] if entry else 0)
                self.refresh()
                if self.tree.exists(saved["id"]):
                    self.tree.selection_set(saved["id"])
                self.show_selected()
                self.status.set("Referência salva na coleção local. Confira sua pertinência antes de coletar no dossiê.")
                self.notebook.select(self.tab)
                close()
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("Salvar referência", str(exc), parent=window)
        def cancel():
            if value() == initial or messagebox.askyesno("Descartar cadastro?", "Há alterações ainda não salvas. Deseja descartá-las?",
                                                        default=messagebox.NO, parent=window):
                close()
        ttk.Button(buttons, text="Salvar referência", command=save).pack(side="left")
        ttk.Button(buttons, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def archive(self):
        entry = self.selected()
        if not entry:
            return
        reason = simpledialog.askstring("Restaurar referência" if entry["archived"] else "Arquivar referência",
                                       "Motivo da alteração (o histórico será preservado):", parent=self.root)
        if reason:
            try:
                self.store.set_archived(entry["id"], entry["revision"], not entry["archived"], reason)
                self.refresh()
                self.status.set("Estado da referência atualizado; o histórico e as seleções anteriores foram preservados.")
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("Alterar referência", str(exc), parent=self.root)

    def use(self):
        entry = self.selected()
        target = self.target
        if not entry or not target:
            return
        pane = self.work.evidence
        if pane.store is not target["store"] or pane.cid != target["cid"]:
            self.clear_target()
            return
        if pane.busy():
            messagebox.showinfo("Pesquisa em andamento", "Aguarde ou cancele a tarefa antes de selecionar outra referência.", parent=self.root)
            return
        try:
            current = self.store.get(entry["id"], entry["revision"], require_active=True)
            target["store"].record_library_reference(target["cid"], target["basis"], current,
                                                     self.query.get(), self.topic_options.get(self.topic.get()))
            pane.url.delete(0, "end")
            pane.url.insert(0, current["url"])
            self.work.refresh()
            pane.progress.configure(text="Referência da coleção selecionada. Use Coletar fonte para arquivar e conferir o documento.")
            self.notebook.select(pane.tab)
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showinfo("Usar referência", str(exc), parent=self.root)
