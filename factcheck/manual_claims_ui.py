"""Inclusão e divisão humanas com origem literal e justificativa."""

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .queue_filters import CATEGORIES
from .topics import load_snapshot


def open_editor(work, split=False):
    if not work.store or work.app.closing:
        return
    claim = work.selected_claim() if split else None
    source = work.store.source(claim["paragraph_id"]) if claim else work.selected_source()
    if not source or split and not claim:
        messagebox.showinfo("Afirmação manual", "Selecione uma fala concluída em Revisar falas, ou uma afirmação atual para dividir.", parent=work.root)
        return
    store = work.store
    try:
        vocabulary = load_snapshot(work.app.project_root)
    except ValueError as exc:
        messagebox.showerror("Afirmação manual", str(exc), parent=work.root)
        return
    window, close = work.dialog("Dividir afirmação" if split else "Incluir afirmação manual")
    window.geometry("850x760")
    window.minsize(740, 680)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Inclua somente citações literais. Esta ação não confere a transcrição nem decide a veracidade. "
              "Na divisão, o original e seu dossiê ficam históricos; cada parte começa sem evidências ou decisão.", wraplength=780).pack(anchor="w")
    original = ScrolledText(frame, height=4, wrap="word")
    original.insert("1.0", claim["quote"] if split else source["text"])
    original.configure(state="disabled")
    original.pack(fill="x", pady=8)
    pages = ttk.Notebook(frame)
    pages.pack(fill="both", expand=True)
    editors = []
    def add():
        if len(editors) >= (12 if split else 1):
            return
        tab = ttk.Frame(pages, padding=10)
        pages.add(tab, text=f"Parte {len(editors)+1}" if split else "Afirmação")
        values = {}
        for key, label in (("quote", "Citação literal"), ("summary", "Resumo fiel")):
            ttk.Label(tab, text=label).pack(anchor="w")
            editor = ScrolledText(tab, height=3, wrap="word")
            editor.pack(fill="both", expand=True, pady=4)
            values[key] = editor
        ttk.Label(tab, text="Categoria").pack(anchor="w")
        values["category"] = ttk.Combobox(tab, values=list(CATEGORIES.values()), state="readonly")
        values["category"].set(CATEGORIES["fato"])
        values["category"].pack(fill="x", pady=4)
        ttk.Label(tab, text="Tema opcional").pack(anchor="w")
        values["topic"] = ttk.Entry(tab)
        values["topic"].pack(fill="x", pady=4)
        editors.append(values)
        pages.select(tab)
    add()
    if split:
        add()
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Adicionar parte", command=add).pack(side="left")
        def remove():
            if len(editors) > 2:
                pages.forget(len(editors)-1)
                editors.pop()
        ttk.Button(row, text="Retirar última parte", command=remove).pack(side="left", padx=8)
    ttk.Label(frame, text="Motivo obrigatório").pack(anchor="w", pady=(8, 0))
    reason = ScrolledText(frame, height=2, wrap="word")
    reason.pack(fill="x", pady=4)
    def value():
        return ([{"quote": values["quote"].get("1.0", "end-1c"), "summary": values["summary"].get("1.0", "end-1c"),
                  "category": next(key for key, label in CATEGORIES.items() if label == values["category"].get()),
                  "topic": values["topic"].get().strip() or None} for values in editors], reason.get("1.0", "end-1c"))
    initial = value()
    def save():
        try:
            fields, explanation = value()
            created = store.create_claims(source["paragraph_id"], source["revision"], fields, explanation, vocabulary,
                {"id": claim["id"], "revision": claim.get("claim_revision", 1)} if split else None)
            work.refresh()
            work.app.notebook.select(work.claim_tab)
            if work.claim_tree.exists(created[0]["id"]):
                work.claim_tree.selection_set(created[0]["id"])
                work.show_claim()
            close()
        except ValueError as exc:
            messagebox.showerror("Afirmação manual", str(exc), parent=window)
    def cancel():
        if value() == initial or messagebox.askyesno("Descartar inclusão?", "Há alterações ainda não salvas. Deseja descartá-las?", default=messagebox.NO, parent=window):
            close()
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=8)
    ttk.Button(row, text="Salvar partes" if split else "Incluir afirmação", command=save).pack(side="left")
    ttk.Button(row, text="Cancelar", command=cancel).pack(side="right")
    window.protocol("WM_DELETE_WINDOW", cancel)
