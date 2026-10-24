"""Busca local de casos com decisão humana e comparação explícita entre contextos."""

from pathlib import Path
import os
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .discovery import search_basis
from .previous_checks import (COMPARISONS, COMPARISON_FIELDS, VERDICTS, PreviousChecksTask,
                              filter_checked_cases, refresh_checked_case, render_previous)
from .queue_filters import field_choices


class PreviousChecksPane:
    def __init__(self, work, notebook):
        self.work, self.root, self.notebook = work, work.root, notebook
        self.task, self.target = None, None
        self.entries, self.visible = {}, {}
        self.warnings = []
        self.tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.tab, text="Checagens anteriores")
        ttk.Label(self.tab, text="Consulte decisões humanas salvas em outras sessões. Correspondência textual apenas indica casos para comparar; "
                  "fontes e validade precisam de nova conferência.", wraplength=920).pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        self.folder = tk.StringVar(value=str(work.app.project_root / "recordings"))
        ttk.Label(row, text="Pasta de sessões").pack(side="left")
        ttk.Entry(row, textvariable=self.folder, state="readonly").pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Escolher pasta", command=self.choose_folder).pack(side="left")
        self.update_button = ttk.Button(row, text="Atualizar consulta", command=self.refresh)
        self.update_button.pack(side="left", padx=8)
        self.cancel_button = ttk.Button(row, text="Cancelar", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="right")
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Buscar").pack(side="left")
        self.query = tk.StringVar()
        ttk.Entry(row, textvariable=self.query).pack(side="left", fill="x", expand=True, padx=8)
        self.topic, self.verdict = tk.StringVar(value="Todos"), tk.StringVar(value="Todas")
        self.topic_options = field_choices([], "Sem tema")
        ttk.Label(row, text="Tema").pack(side="left")
        self.topic_box = ttk.Combobox(row, textvariable=self.topic, values=list(self.topic_options), state="readonly", width=18)
        self.topic_box.pack(side="left", padx=8)
        ttk.Label(row, text="Decisão anterior").pack(side="left")
        ttk.Combobox(row, textvariable=self.verdict, values=["Todas", *VERDICTS.values()], state="readonly", width=15).pack(side="left", padx=8)
        self.historical = tk.BooleanVar(value=False)
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=4)
        ttk.Checkbutton(row, text="Incluir casos históricos / descartados", variable=self.historical).pack(side="left")
        ttk.Button(row, text="Limpar filtros", command=self.reset_filters).pack(side="left", padx=8)
        ttk.Button(row, text="Abrir pasta de origem", command=self.open_folder).pack(side="left", padx=8)
        self.warnings_button = ttk.Button(row, text="Ver avisos", command=self.show_warnings, state="disabled")
        self.warnings_button.pack(side="left")
        self.compare_button = ttk.Button(row, text="Comparar com dossiê atual", command=self.compare, state="disabled")
        self.compare_button.pack(side="right")
        self.destination = tk.StringVar(value="Para associar um antecedente, abra esta consulta pelo dossiê desejado.")
        ttk.Label(self.tab, textvariable=self.destination, wraplength=920).pack(anchor="w", pady=4)
        self.status = tk.StringVar(value="Use Atualizar consulta. A leitura não altera nem recupera automaticamente as sessões.")
        ttk.Label(self.tab, textvariable=self.status, wraplength=920).pack(anchor="w", pady=4)
        self.tree = work.tree(self.tab, [("date", "Decisão em", 155), ("event", "Evento", 175), ("state", "Origem", 100),
            ("verdict", "Decisão anterior", 115), ("text", "Afirmação", 450)], height=5)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        self.preview = ScrolledText(self.tab, wrap="word", height=10, font=("Segoe UI", 10))
        self.preview.pack(fill="both", expand=True, pady=6)
        self.preview.configure(state="disabled")
        for variable in (self.query, self.topic, self.verdict, self.historical):
            variable.trace_add("write", lambda *_: self.apply_filters())

    def busy(self):
        return bool(self.task and self.task.pending)

    def choose_folder(self):
        if self.busy():
            return
        folder = filedialog.askdirectory(parent=self.root, title="Pasta que contém as subpastas de sessões", initialdir=self.folder.get())
        if folder:
            self.folder.set(folder)
            self.entries, self.visible = {}, {}
            self.warnings = []
            self.warnings_button.configure(state="disabled")
            self.apply_filters()
            self.refresh()

    def refresh(self):
        if self.busy() or self.work.app.closing:
            return
        self.task = PreviousChecksTask(Path(self.folder.get()), lambda kind, data: self.work.app.events.put((kind, data)))
        self.work.app.register_activity(self.task.token, "Consulta de checagens anteriores", self.task.cancel)
        self.update_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set("Consultando bancos locais em segundo plano. A captura pode continuar.")
        self.task.start()

    def done(self, data):
        self.work.app.activities.pop(data["token"], None)
        if not self.task or data["token"] != self.task.token:
            return
        self.update_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if self.task.cancelled.is_set() or not data["success"]:
            self.status.set(data.get("message", "Consulta cancelada. A lista anterior foi preservada."))
            return
        self.entries = {entry["key"]: entry for entry in data["entries"]}
        self.warnings = data["warnings"]
        self.warnings_button.configure(state="normal" if self.warnings else "disabled")
        selected = self.topic_options.get(self.topic.get())
        self.topic_options = field_choices((entry["snapshot"]["claim"].get("topic") for entry in self.entries.values()), "Sem tema")
        label = next((label for label, value in self.topic_options.items() if value == selected), None)
        if label is None:
            label = self.topic.get()
            self.topic_options[label] = selected
        self.topic_box.configure(values=list(self.topic_options))
        self.topic.set(label)
        self.apply_filters()
        self.status.set(f"{len(self.entries)} casos com decisão · {data['sessions']} sessões lidas · {len(data['warnings'])} avisos. "
                        "Atualize após mudanças nas sessões; a consulta não verifica validade online.")

    def show_warnings(self):
        if not self.warnings or self.work.app.closing:
            return
        window, close = self.work.dialog("Avisos da consulta de checagens anteriores")
        text = ScrolledText(window, wrap="word")
        text.pack(fill="both", expand=True, padx=16, pady=16)
        text.insert("1.0", "\n\n".join(self.warnings))
        text.configure(state="disabled")
        ttk.Button(window, text="Fechar", command=close).pack(pady=12)

    def cancel(self):
        if self.busy() and messagebox.askyesno("Cancelar consulta?", "Deseja cancelar a consulta? A lista anterior será preservada.",
                                               default=messagebox.NO, parent=self.root):
            self.task.cancel()

    def reset_filters(self):
        self.query.set("")
        self.topic.set("Todos")
        self.verdict.set("Todas")
        self.historical.set(False)

    def apply_filters(self):
        rows = filter_checked_cases(self.entries.values(), self.query.get(), self.topic_options.get(self.topic.get()),
            next((key for key, label in VERDICTS.items() if label == self.verdict.get()), None), self.historical.get())
        self.visible = {entry["key"]: entry for entry in rows}
        self.work._rows(self.tree, {entry["key"]: (entry["snapshot"]["decision"]["at"], entry["snapshot"]["event"].get("title", ""),
            "Atual na origem" if entry["snapshot"]["source_current"] else "Histórica", VERDICTS[entry["snapshot"]["decision"]["verdict"]],
            entry["snapshot"]["claim"]["summary"]) for entry in rows})
        self.show_selected()

    def selected(self):
        selection = self.tree.selection()
        return self.visible.get(selection[0]) if selection else None

    def show_selected(self):
        entry = self.selected()
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", render_previous(entry["snapshot"]) if entry else f"{len(self.visible)} casos exibidos de {len(self.entries)}. Selecione um caso para consultar o contexto.")
        self.preview.configure(state="disabled")
        self.compare_button.configure(state="normal" if entry and self.target and not self.work.app.closing else "disabled")

    def open_folder(self):
        entry = self.selected()
        if entry and Path(entry["folder"]).is_dir():
            os.startfile(entry["folder"])

    def clear_target(self):
        self.target = None
        self.destination.set("Para associar um antecedente, abra esta consulta pelo dossiê desejado.")
        self.show_selected()

    def open_for_case(self):
        pane = self.work.evidence
        if not pane.store or not pane.cid:
            return
        data = pane.store.snapshot(pane.cid)
        if not data["valid"]:
            messagebox.showinfo("Checagens anteriores", "Abra uma afirmação atual antes de comparar casos.", parent=self.root)
            return
        self.target = {"store": pane.store, "cid": pane.cid, "basis": search_basis(data["claim"], data.get("plan"))}
        self.destination.set("Destino: " + data["claim"]["summary"][:200])
        self.show_selected()
        self.notebook.select(self.tab)

    def compare(self):
        entry, target = self.selected(), self.target
        if not entry or not target or self.work.app.closing:
            return
        pane = self.work.evidence
        if pane.store is not target["store"] or pane.cid != target["cid"]:
            self.clear_target()
            return
        try:
            origin = refresh_checked_case(entry)
            current = target["store"].snapshot(target["cid"])
            if not current["valid"] or target["basis"] != search_basis(current["claim"], current.get("plan")):
                raise ValueError("O destino mudou. Reabra a consulta pelo dossiê atual.")
        except (ValueError, OSError, sqlite3.Error) as exc:
            messagebox.showinfo("Comparar checagens", str(exc), parent=self.root)
            return
        window, close = self.work.dialog("Comparar checagem anterior · contextos e validade")
        window.geometry("920x780")
        window.minsize(840, 700)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Registre diferenças e pendências. Salvar mantém o antecedente como referência de pesquisa; "
                  "evidências e decisão do caso atual são registradas no dossiê.", wraplength=790).pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom", pady=(8, 0))
        outcome = ttk.Combobox(frame, values=list(COMPARISONS.values()), state="readonly")
        outcome.set(COMPARISONS["a_conferir"])
        outcome.pack(fill="x", pady=4)
        tabs = ttk.Notebook(frame)
        tabs.pack(fill="both", expand=True)
        context, notes = ttk.Frame(tabs, padding=10), ttk.Frame(tabs, padding=10)
        tabs.add(context, text="Contextos de origem e destino")
        tabs.add(notes, text="Comparação e pendências")
        text = ScrolledText(context, wrap="word", font=("Segoe UI", 10))
        text.pack(fill="both", expand=True)
        text.insert("1.0", "CASO ATUAL\n" + f"{current['debate']['title']} · {current['debate']['event_date']}\n" +
            f"Participante: {current['claim'].get('speaker') or 'Não identificado'}\n" + current["claim"]["quote"] +
            "\nContexto: " + current["claim"].get("context", "") + "\n\nPlano atual:\n" +
            "\n".join(f"{label}: {(current.get('plan') or {}).get(key) or 'Não definido'}" for key, label in
                        (("period", "Período"), ("territory", "Território"), ("indicator", "Indicador"), ("comparison", "Comparação"), ("notes", "Notas")))
            + "\n\nANTECEDENTE\n" + render_previous(origin))
        text.configure(state="disabled")
        fields = {}
        for key, label in COMPARISON_FIELDS.items():
            ttk.Label(notes, text=label + " · obrigatório; registre o que faltar conferir").pack(anchor="w", pady=(4, 0))
            fields[key] = ScrolledText(notes, height=2, wrap="word")
            fields[key].pack(fill="both", expand=True, pady=3)
        def values():
            return {"outcome": next(key for key, label in COMPARISONS.items() if label == outcome.get()),
                    **{key: field.get("1.0", "end-1c") for key, field in fields.items()}}
        initial = values()
        query = self.query.get()
        def save():
            try:
                if pane.store is not target["store"] or pane.cid != target["cid"]:
                    raise ValueError("A sessão ou o dossiê de destino mudou. Reabra a comparação.")
                fresh = refresh_checked_case(entry)
                target["store"].record_previous_check(target["cid"], target["basis"], fresh, values(), query)
                self.work.refresh()
                self.status.set("Antecedente e comparação registrados no dossiê. Fontes e decisão atuais continuam independentes.")
                self.notebook.select(pane.tab)
                close()
            except (ValueError, OSError, sqlite3.Error) as exc:
                messagebox.showinfo("Registrar antecedente", str(exc), parent=window)
        def cancel():
            if values() == initial or messagebox.askyesno("Descartar comparação?", "Há alterações ainda não salvas. Deseja descartá-las?",
                                                         default=messagebox.NO, parent=window):
                close()
        ttk.Button(buttons, text="Registrar antecedente consultado", command=save).pack(side="left")
        ttk.Button(buttons, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)
