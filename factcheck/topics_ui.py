"""Cadastro de temas compartilhado entre sessões, independente das decisões factuais."""

import sqlite3
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .topics import TopicStore, key, load_snapshot


class TopicsPane:
    def __init__(self, work, notebook):
        self.work, self.root, self.notebook = work, work.root, notebook
        self.store = None
        self.entries, self.visible, self.histories = {}, {}, {}
        self.tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab, text="Temas")
        ttk.Label(self.tab, text="Nomes e variações de escrita para organizar a triagem e sugerir temas na revisão. "
                  "O cadastro não classifica falas por significado nem decide fatos. Alterações não reescrevem casos anteriores.",
                  wraplength=920).pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Buscar").pack(side="left")
        self.query = tk.StringVar()
        ttk.Entry(row, textvariable=self.query).pack(side="left", fill="x", expand=True, padx=8)
        self.archived = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Incluir arquivados", variable=self.archived).pack(side="right")
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Novo tema", command=self.edit).pack(side="left")
        self.edit_button = ttk.Button(row, text="Editar tema", command=self.edit_selected, state="disabled")
        self.edit_button.pack(side="left", padx=8)
        self.archive_button = ttk.Button(row, text="Arquivar / restaurar", command=self.archive, state="disabled")
        self.archive_button.pack(side="left")
        ttk.Button(row, text="Atualizar lista", command=self.refresh).pack(side="left", padx=8)
        ttk.Button(row, text="Limpar filtros", command=self.reset_filters).pack(side="right")
        self.status = tk.StringVar(value="Cadastre os temas da sua equipe. Sem cadastro, os temas livres continuam disponíveis.")
        ttk.Label(self.tab, textvariable=self.status, wraplength=920).pack(anchor="w", pady=6)
        self.tree = work.tree(self.tab, [("state", "Estado", 100), ("text", "Tema", 260), ("aliases", "Variações de escrita", 430),
                                        ("revision", "Versão", 70)], height=6)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        self.preview = ScrolledText(self.tab, wrap="word", height=10, font=("Segoe UI", 10))
        self.preview.pack(fill="both", expand=True, pady=(10, 0))
        self.preview.configure(state="disabled")
        for variable in (self.query, self.archived):
            variable.trace_add("write", lambda *_: self.apply_filters())
        notebook.bind("<<NotebookTabChanged>>", self.tab_changed, add="+")

    def tab_changed(self, _=None):
        if self.notebook.select() == str(self.tab):
            self.refresh()

    def ensure_store(self):
        if self.store is not None:
            return True
        try:
            self.store = TopicStore(self.work.app.project_root / "library")
            return True
        except (ValueError, OSError, sqlite3.Error):
            self.status.set("Não foi possível abrir os temas. Confira acesso e espaço na pasta library; a captura pode continuar.")
            return False

    def refresh(self):
        if not self.ensure_store():
            return
        try:
            snapshot = load_snapshot(self.work.app.project_root)
            self.entries = {entry["id"]: entry for entry in self.store.entries()}
            self.histories = {}
            self.apply_filters()
            self.status.set(f"Vocabulário · revisão {snapshot['revision']} · {len(snapshot['topics'])} temas ativos. "
                            "Nome ou variação pertence a um só tema; arquivados reservam seus termos.")
        except (ValueError, OSError, sqlite3.Error):
            self.status.set("Não foi possível ler os temas. Confira a pasta library e atualize a lista.")

    def reset_filters(self):
        self.query.set("")
        self.archived.set(False)

    def apply_filters(self):
        words = key(self.query.get()).split()
        self.visible = {tid: entry for tid, entry in self.entries.items() if (self.archived.get() or not entry["archived"])
                        and all(word in key(" ".join([entry["name"], *entry["aliases"], entry["description"]])) for word in words)}
        self.work._rows(self.tree, {tid: ("Arquivado" if entry["archived"] else "Ativo", entry["name"], "; ".join(entry["aliases"]),
                               entry["revision"]) for tid, entry in self.visible.items()})
        self.show_selected()

    def selected(self):
        selected = self.tree.selection()
        return self.visible.get(selected[0]) if selected else None

    @staticmethod
    def describe(entry):
        return (f"{entry['name']} · tema {entry['id']} · versão {entry['revision']}\n"
                f"Variações: {'; '.join(entry['aliases']) or 'Não cadastradas'}\n"
                f"Descrição: {entry['description'] or 'Não informada'}\nMotivo: {entry['reason']}\nAtualizado em: {entry['updated_at']}")

    def show_selected(self):
        entry = self.selected()
        self.edit_button.configure(state="normal" if entry else "disabled")
        self.archive_button.configure(state="normal" if entry else "disabled", text="Restaurar tema" if entry and entry["archived"] else "Arquivar tema")
        text = f"{len(self.visible)} de {len(self.entries)} temas exibidos. Selecione um tema para consultar suas versões."
        if entry:
            text = self.describe(entry) + "\n\nHistórico do cadastro:\n"
            try:
                if entry["id"] not in self.histories:
                    self.histories[entry["id"]] = self.store.history(entry["id"])
                labels = {"created": "Cadastro", "edited": "Edição", "archived": "Arquivamento", "restored": "Restauração"}
                for change in self.histories[entry["id"]]:
                    text += f"\n{labels[change['action']]} · vocabulário {change['vocabulary_revision']}\n{self.describe(change['current'])}\n"
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

    def edit(self, entry=None):
        if not self.ensure_store() or self.work.app.closing:
            return
        window, close = self.work.dialog("Editar tema" if entry else "Novo tema")
        window.geometry("780x670")
        window.minsize(700, 610)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Informe variações que devem receber o mesmo nome. Maiúsculas, acentos e espaços são ignorados na correspondência. "
                  "A descrição orienta a equipe; não é enviada ao modelo.", wraplength=650).pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(frame)
        buttons.pack(side="bottom", fill="x", pady=(10, 0))
        if entry and entry["archived"]:
            ttk.Label(frame, text="Tema arquivado; editar não o restaura.").pack(anchor="w", pady=4)
        ttk.Label(frame, text="Nome do tema · até 100 caracteres").pack(anchor="w")
        name = ttk.Entry(frame)
        name.pack(fill="x", pady=5)
        name.insert(0, entry["name"] if entry else "")
        ttk.Label(frame, text="Variações de escrita · até doze, separadas por ponto e vírgula").pack(anchor="w")
        aliases = ttk.Entry(frame)
        aliases.pack(fill="x", pady=5)
        aliases.insert(0, "; ".join(entry["aliases"]) if entry else "")
        ttk.Label(frame, text="Descrição e limites do tema · opcional").pack(anchor="w")
        description = ScrolledText(frame, height=5, wrap="word")
        description.pack(fill="both", expand=True, pady=5)
        description.insert("1.0", entry["description"] if entry else "")
        ttk.Label(frame, text="Motivo obrigatório do cadastro ou alteração").pack(anchor="w")
        reason = ScrolledText(frame, height=3, wrap="word")
        reason.pack(fill="both", expand=True, pady=5)
        reason.insert("1.0", entry["reason"] if entry else "")
        def values():
            return {"name": name.get(), "aliases": [value.strip() for value in aliases.get().split(";") if value.strip()],
                    "description": description.get("1.0", "end-1c")}, reason.get("1.0", "end-1c")
        initial = values()
        def save():
            try:
                fields, explanation = values()
                saved = self.store.save(fields, explanation, entry["id"] if entry else None, entry["revision"] if entry else 0)
                self.refresh()
                if self.tree.exists(saved["id"]):
                    self.tree.selection_set(saved["id"])
                self.show_selected()
                close()
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("Salvar tema", str(exc), parent=window)
        def cancel():
            if values() == initial or messagebox.askyesno("Descartar cadastro de tema?", "Há alterações ainda não salvas. Deseja descartá-las?",
                                                         default=messagebox.NO, parent=window):
                close()
        ttk.Button(buttons, text="Salvar tema", command=save).pack(side="left")
        ttk.Button(buttons, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def archive(self):
        entry = self.selected()
        if not entry:
            return
        reason = simpledialog.askstring("Restaurar tema" if entry["archived"] else "Arquivar tema", "Motivo da alteração:", parent=self.root)
        if reason:
            try:
                self.store.set_archived(entry["id"], entry["revision"], not entry["archived"], reason)
                self.refresh()
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showerror("Alterar tema", str(exc), parent=self.root)
