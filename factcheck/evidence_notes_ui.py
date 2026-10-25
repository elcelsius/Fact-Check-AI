"""Editor de evidências selecionadas, cálculos e contexto das fontes."""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .evidence_notes import RELATIONS


def open_notes(pane):
    if not pane.store or not pane.cid or pane.app.closing:
        return
    store, cid = pane.store, pane.cid
    data = store.snapshot(cid)
    if not data["valid"]:
        messagebox.showinfo("Evidências", "Selecione uma afirmação atual.", parent=pane.root)
        return
    window, close = pane.work.dialog("Evidências, cálculos e contexto das fontes")
    window.geometry("900x820")
    window.minsize(800, 730)
    frame = ttk.Frame(window, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Anotações não são decisões factuais. Salvar invalida conclusões anteriores. "
              "Mudanças na fonte ou no recorte exigem nova conferência.", wraplength=850).pack(anchor="w")
    listing = ttk.Treeview(frame, columns=("type", "state", "text"), show="headings", height=3)
    for key, label, width in (("type", "Tipo", 120), ("state", "Situação", 160), ("text", "Explicação", 550)):
        listing.heading(key, text=label)
        listing.column(key, width=width)
    for note in data["work_notes"]:
        listing.insert("", "end", iid=note["id"], values=(note["kind"], "Atual" if note["current"] else "Retirada / a conferir", note["explanation"]))
    listing.pack(fill="x", pady=6)
    def retire():
        if not listing.selection(): return
        reason = simpledialog.askstring("Retirar anotação", "Motivo da retirada:", parent=window)
        if reason:
            try:
                store.retire_note(cid, data["revision"], listing.selection()[0], reason)
                pane.work.refresh()
                close()
            except ValueError as exc:
                messagebox.showerror("Retirar anotação", str(exc), parent=window)
    ttk.Button(frame, text="Retirar anotação selecionada", command=retire).pack(anchor="w")
    docs = {f"{doc['id']} · {doc['title'][:80]}": doc for doc in data["documents"]}
    ttk.Label(frame, text="Fonte coletada · para citação ou contexto").pack(anchor="w", pady=(8, 2))
    document = ttk.Combobox(frame, values=list(docs), state="readonly")
    document.pack(fill="x")
    if docs: document.current(0)
    pages = ttk.Notebook(frame)
    pages.pack(fill="both", expand=True, pady=6)
    citation, arithmetic, context = [ttk.Frame(pages, padding=10) for _ in range(3)]
    for tab, title in ((citation, "Citação"), (arithmetic, "Cálculo"), (context, "Contexto da fonte")):
        pages.add(tab, text=title)
    block = ttk.Combobox(citation, state="readonly")
    block.pack(fill="x")
    quote = ScrolledText(citation, height=7, wrap="word")
    quote.pack(fill="both", expand=True, pady=6)
    relation = ttk.Combobox(citation, values=list(RELATIONS.values()), state="readonly")
    relation.set(RELATIONS["contextualiza"])
    relation.pack(fill="x")
    blocks = {}
    def set_quote(*_):
        quote.delete("1.0", "end")
        if block.get() in blocks: quote.insert("1.0", blocks[block.get()]["text"])
    def set_doc(*_):
        blocks.clear()
        blocks.update({f"{row['id']} · {row['locator']}": row for row in docs.get(document.get(), {}).get("blocks", [])})
        block.configure(values=list(blocks))
        if blocks: block.current(0)
        set_quote()
    document.bind("<<ComboboxSelected>>", set_doc)
    block.bind("<<ComboboxSelected>>", set_quote)
    set_doc()
    def entry(parent, label):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(5, 2))
        widget = ttk.Entry(parent)
        widget.pack(fill="x")
        return widget
    formula = entry(arithmetic, "Fórmula · variáveis, números, parênteses e + - * /")
    unit = entry(arithmetic, "Unidade · %, p.p., pessoas etc.")
    ttk.Label(arithmetic, text="Variáveis · nome=valor, uma por linha, sem separador de milhar").pack(anchor="w", pady=4)
    variables = ScrolledText(arithmetic, height=3, wrap="word")
    variables.pack(fill="x")
    ttk.Label(arithmetic, text="Citações atuais usadas · Ctrl/Shift para selecionar").pack(anchor="w", pady=4)
    citations = [note for note in data["work_notes"] if note["kind"] == "citation" and note["current"]]
    anchors = tk.Listbox(arithmetic, height=3, selectmode="extended", exportselection=False)
    for note in citations: anchors.insert("end", note["quote"][:150])
    anchors.pack(fill="both", expand=True)
    context_fields = {key: entry(context, label) for key, label in (
        ("period", "Período dos dados"), ("available_on", "Disponível em · AAAA-MM-DD ou vazio se desconhecido"),
        ("common_origin", "Origem comum · documento ou metodologia reproduzida por outras fontes"))}
    ttk.Label(frame, text="Explicação obrigatória · recorte, método e limites").pack(anchor="w")
    explanation = ScrolledText(frame, height=3, wrap="word")
    explanation.pack(fill="x", pady=4)
    def value():
        return (document.get(), pages.index(pages.select()), block.get(), quote.get("1.0", "end-1c"), relation.get(),
                formula.get(), unit.get(), variables.get("1.0", "end-1c"), tuple(anchors.curselection()),
                tuple(widget.get() for widget in context_fields.values()), explanation.get("1.0", "end-1c"))
    initial = value()
    def save():
        try:
            selected = pages.index(pages.select())
            fields = {"explanation": explanation.get("1.0", "end-1c")}
            if selected == 1:
                values = {}
                for line in variables.get("1.0", "end-1c").splitlines():
                    if not line.strip(): continue
                    key, sep, number = line.partition("=")
                    if not sep or key.strip() in values: raise ValueError("Use variáveis distintas no formato nome=valor.")
                    values[key.strip()] = number.strip()
                fields.update(formula=formula.get(), unit=unit.get(), variables=values, note_ids=[citations[i]["id"] for i in anchors.curselection()])
                kind = "calculation"
            else:
                if document.get() not in docs: raise ValueError("Escolha uma fonte coletada.")
                fields["document_id"] = docs[document.get()]["id"]
                if selected == 0:
                    if block.get() not in blocks: raise ValueError("Escolha um bloco do documento.")
                    fields.update(block_id=blocks[block.get()]["id"], quote=quote.get("1.0", "end-1c"), relation=next(key for key, label in RELATIONS.items() if label == relation.get()))
                    kind = "citation"
                else:
                    fields.update({key: widget.get().strip() for key, widget in context_fields.items()})
                    kind = "source_context"
            store.save_note(cid, data["revision"], kind, fields)
            pane.work.refresh()
            close()
        except ValueError as exc:
            messagebox.showerror("Registrar anotação", str(exc), parent=window)
    def cancel():
        if value() == initial or messagebox.askyesno("Descartar anotações?", "Há alterações não salvas. Deseja descartá-las?", default=messagebox.NO, parent=window): close()
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=6)
    ttk.Button(row, text="Salvar anotação", command=save).pack(side="left")
    ttk.Button(row, text="Cancelar", command=cancel).pack(side="right")
    window.protocol("WM_DELETE_WINDOW", cancel)
