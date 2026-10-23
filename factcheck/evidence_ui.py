"""Painel de fontes, dossiê interno e revisão humana."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from urllib.parse import urlencode
import webbrowser

from .dossiers import DossierStore, VERDICTS, render
from .research import ResearchTask
from .sources import search_plan, source_url


class EvidencePane:
    def __init__(self, workbench, notebook):
        self.work = workbench
        self.app, self.root = workbench.app, workbench.root
        self.store, self.cid, self.task = None, None, None
        self.notebook = notebook
        self.tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab, text="Dossiê e fontes")
        self.claim_label = ttk.Label(self.tab, text="Selecione uma afirmação e clique em Abrir dossiê.", wraplength=950)
        self.claim_label.pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        self.query = ttk.Combobox(row)
        self.query.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Buscar no navegador", command=self.search).pack(side="left", padx=(8, 0))
        ttk.Label(self.tab, text="Consulte dados, metodologia e versões divergentes. Resultados de busca só entram como evidência após a coleta da fonte.", wraplength=950).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        self.url = ttk.Entry(row)
        self.url.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Coletar fonte", command=self.collect).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Importar PDF/HTML", command=self.import_document).pack(side="left", padx=(8, 0))
        ttk.Label(self.tab, text="Cole a URL HTTPS de uma página ou PDF institucional. Coleção inicial: gov.br, jus.br, leg.br, OMS, Banco Mundial, FMI, OCDE e ONU.", wraplength=950).pack(anchor="w", pady=4)
        self.documents = ttk.Treeview(self.tab, columns=("title", "source", "date"), show="headings", height=4, selectmode="browse")
        for key, label, width in (("title", "Fonte coletada", 520), ("source", "Instituição", 220), ("date", "Publicação", 140)):
            self.documents.heading(key, text=label)
            self.documents.column(key, width=width, minwidth=70)
        self.documents.pack(fill="x", pady=6)
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        for label, command in (("Ler cópia extraída", self.read_document), ("Abrir fonte", self.open_document), ("Retirar fonte", self.remove_document),
                               ("Analisar com Gemini", self.analyze), ("Cancelar pesquisa", self.cancel)):
            ttk.Button(row, text=label, command=command).pack(side="left", padx=(0, 6))
        self.progress = ttk.Label(self.tab, text="Nenhuma pesquisa em andamento.", wraplength=950)
        self.progress.pack(anchor="w", pady=4)
        self.preview = ScrolledText(self.tab, wrap="word", height=13, font=("Segoe UI", 10))
        self.preview.pack(fill="both", expand=True, pady=6)
        self.preview.configure(state="disabled")
        row = ttk.Frame(self.tab)
        row.pack(fill="x", side="bottom", before=self.preview, pady=4)
        ttk.Button(row, text="Registrar decisão humana", command=self.decide).pack(side="left")
        ttk.Button(row, text="Exportar dossiê interno", command=self.export).pack(side="left", padx=8)
        ttk.Label(row, text="Sem divulgação automática.").pack(side="right")

    def busy(self):
        return bool(self.task and self.task.pending)

    def load(self, review):
        self.store = DossierStore(review)
        self.store.recover()
        self.cid = None
        self.documents.delete(*self.documents.get_children())
        self.query.set("")
        self.query.configure(values=[])
        self.claim_label.configure(text="Selecione uma afirmação e clique em Abrir dossiê.")
        self.show_text("")

    def open_selected(self):
        claim = self.work.selected_claim()
        if not claim:
            return
        self.cid = claim["id"]
        self.query.configure(values=search_plan(claim))
        self.query.current(0)
        self.refresh()
        self.notebook.select(self.tab)

    def show_text(self, value):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", value)
        self.preview.configure(state="disabled")

    def refresh(self):
        if not self.store or not self.cid:
            return
        snapshot = self.store.snapshot(self.cid)
        claim = snapshot["claim"]
        self.claim_label.configure(text=f"{claim['speaker'] or 'Não identificado'} · {claim['quote'][:200]}" +
                                   (" · DESATUALIZADO" if not snapshot["valid"] else ""))
        self.work._rows(self.documents, {doc["id"]: (doc["title"], doc["institution"] + (" · cópia importada" if doc.get("acquisition") == "local_import" else ""), doc["published_at"] or "Não identificada") for doc in snapshot["documents"]})
        # A prévia preserva análise e decisão visíveis; a cópia e a exportação têm todo o texto coletado.
        preview = json.loads(json.dumps(snapshot))
        for doc in preview["documents"]:
            doc["blocks"] = [{**block, "text": block["text"][:1600]} for block in doc["blocks"][:2]]
            doc["warnings"].append("Prévia reduzida. Use Ler cópia extraída para consultar todos os trechos.")
        self.show_text(render(preview))

    def search(self):
        query = self.query.get().strip()
        if self.store and self.cid and query:
            self.store.record_query(self.cid, query[:1000])
            webbrowser.open("https://www.google.com/search?" + urlencode({"q": query[:1000]}))

    def collect(self):
        try:
            self.start("collect", source_url(self.url.get().strip()))
        except ValueError as exc:
            messagebox.showerror("Coletar fonte", str(exc), parent=self.root)

    def analyze(self):
        if self.work.ai_config.provider != "gemini":
            messagebox.showinfo("Analisar evidências", "Configure Gemini em Configurar IA para usar a análise automática. "
                                "A coleta, a leitura e a revisão humana funcionam sem chave.", parent=self.root)
            return
        if self.work.runner and self.work.runner.pending:
            messagebox.showinfo("Analisar evidências", "Aguarde ou cancele a triagem antes de solicitar esta análise ao Gemini.", parent=self.root)
            return
        self.start("analyze", "")

    def import_document(self):
        if not self.store or not self.cid or self.app.closing:
            return
        if self.busy():
            messagebox.showinfo("Importar documento", "Aguarde ou cancele a pesquisa em andamento.", parent=self.root)
            return
        try:
            url = source_url(self.url.get().strip())
        except ValueError:
            messagebox.showinfo("Importar documento", "Primeiro informe a URL institucional de origem no campo da fonte. A cópia será identificada como fornecida pelo operador, sem consulta à URL.", parent=self.root)
            return
        filename = filedialog.askopenfilename(parent=self.root, title="Importar cópia já baixada",
                                             filetypes=[("Documentos PDF e HTML", "*.pdf *.html *.htm"), ("PDF", "*.pdf"), ("HTML", "*.html *.htm")])
        if filename:
            self.start("import", {"path": filename, "url": url})

    def start(self, kind, argument):
        if not self.store or not self.cid or self.app.closing:
            return
        if self.busy():
            messagebox.showinfo("Pesquisa", "Aguarde ou cancele a pesquisa em andamento.", parent=self.root)
            return
        try:
            if kind == "analyze":
                snapshot = self.store.snapshot(self.cid)
                if snapshot["claim"]["category"] != "fato":
                    raise ValueError("A análise factual exige uma declaração classificada como fato. Revise a origem e a triagem.")
            task = ResearchTask(self.store, self.cid, kind, argument, self.work.ai_config,
                                lambda event, data: self.app.events.put((event, data)))
            self.app.register_activity(task.token, "Pesquisa de evidências", task.cancel)
            self.task = task
            self.progress.configure(text="Coletando o documento…" if kind == "collect" else "Importando cópia local. A origem online precisará ser conferida." if kind == "import" else "Preparando análise preliminar. Fala e trechos coletados serão enviados ao Gemini.")
            task.start()
        except (ValueError, RuntimeError) as exc:
            self.progress.configure(text=str(exc))

    def cancel(self):
        if self.busy() and messagebox.askyesno("Cancelar pesquisa", "Cancelar a coleta ou análise em andamento? Fontes e resultados já salvos serão preservados.", default=messagebox.NO, parent=self.root):
            self.task.cancel()

    def done(self, data):
        self.app.activities.pop(data["token"], None)
        if self.task and data["token"] == self.task.token:
            self.progress.configure(text=data["message"])
        self.work.refresh()

    def selected_document(self):
        selected = self.documents.selection()
        if selected and self.cid:
            return next((doc for doc in self.store.snapshot(self.cid)["documents"] if doc["id"] == selected[0]), None)

    def open_document(self):
        doc = self.selected_document()
        if doc:
            webbrowser.open(source_url(doc["url"]))

    def read_document(self):
        doc = self.selected_document()
        if not doc:
            return
        window, close = self.work.dialog("Cópia extraída · " + doc["title"][:80])
        view = ScrolledText(window, wrap="word", font=("Segoe UI", 11))
        view.pack(fill="both", expand=True, padx=12, pady=12)
        view.insert("1.0", doc["url"] + "\n\n" + "\n".join(doc["warnings"]) + "\n\n" +
                    "\n\n".join(f"[{b['id']}] {b['locator']}\n{b['text']}" for b in doc["blocks"]))
        view.configure(state="disabled")
        ttk.Button(window, text="Fechar", command=close).pack(pady=8)
        window.protocol("WM_DELETE_WINDOW", close)

    def remove_document(self):
        doc = self.selected_document()
        if not doc:
            return
        snapshot = self.store.snapshot(self.cid)
        reason = simpledialog.askstring("Retirar fonte", "Motivo da retirada (a análise e a decisão serão invalidadas):", parent=self.root)
        if reason:
            try:
                self.store.remove_document(self.cid, snapshot["revision"], doc["id"], reason)
                self.work.refresh()
            except ValueError as exc:
                messagebox.showerror("Retirar fonte", str(exc), parent=self.root)

    def decide(self):
        if not self.store or not self.cid:
            return
        snapshot = self.store.snapshot(self.cid)
        if not snapshot["valid"]:
            messagebox.showinfo("Revisar dossiê", "A afirmação está desatualizada. Abra a triagem da revisão atual.", parent=self.root)
            return
        window, close = self.work.dialog("Decisão humana · dossiê interno")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Responsável pela revisão").pack(anchor="w")
        name = ttk.Entry(frame)
        name.pack(fill="x", pady=6)
        verdict = ttk.Combobox(frame, state="readonly", values=list(VERDICTS.values()))
        verdict.set("Inconclusiva")
        verdict.pack(fill="x", pady=6)
        ttk.Label(frame, text="Justificativa, fontes utilizadas e limitações").pack(anchor="w", pady=6)
        reason = ScrolledText(frame, wrap="word", height=10)
        reason.pack(fill="both", expand=True)
        checked = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Conferi as fontes, o período, o território, o indicador e a metodologia", variable=checked).pack(anchor="w", pady=12)
        ttk.Label(frame, text="Nova evidência ou análise invalida esta decisão e exige nova revisão. Este registro não publica o dossiê.", wraplength=780).pack(anchor="w", pady=6)

        def save():
            try:
                classification = next(key for key, label in VERDICTS.items() if label == verdict.get())
                if classification != "inconclusiva" and not checked.get():
                    raise ValueError("Confira as fontes e os recortes antes de concluir.")
                self.store.decide(snapshot["claim"]["id"], snapshot["revision"], classification, name.get(), reason.get("1.0", "end-1c"))
                self.refresh()
                self.work.refresh()
                close()
            except ValueError as exc:
                messagebox.showerror("Decisão humana", str(exc), parent=window)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=10)
        ttk.Button(row, text="Salvar decisão", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=close).pack(side="right")
        def confirm_close():
            changed = bool(name.get().strip() or reason.get("1.0", "end-1c").strip() or checked.get() or verdict.get() != "Inconclusiva")
            if not changed or messagebox.askyesno("Descartar revisão?", "A decisão ainda não foi salva. Deseja descartar as alterações?", default=messagebox.NO, parent=window):
                close()
        window.protocol("WM_DELETE_WINDOW", confirm_close)

    def export(self):
        if not self.store or not self.cid:
            return
        snapshot = self.store.snapshot(self.cid)
        filename = filedialog.asksaveasfilename(parent=self.root, title="Exportar para revisão interna", defaultextension=".md",
                                              initialfile=f"dossie-{self.cid[:8]}-r{snapshot['revision']}.md", filetypes=[("Markdown", "*.md")])
        if filename:
            try:
                Path(filename).write_text(render(snapshot), encoding="utf8")
                self.progress.configure(text="Dossiê exportado para revisão interna.")
            except OSError:
                messagebox.showerror("Exportar dossiê", "Não foi possível gravar o arquivo escolhido.", parent=self.root)
