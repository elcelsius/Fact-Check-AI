"""Busca opcional e revisão de candidatas, separadas das fontes coletadas."""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .discovery import SearchConfig
from .sources import source_url


class DiscoveryDialog:
    def __init__(self, pane):
        self.pane, self.cid = pane, pane.cid
        self.window, self._close = pane.work.dialog("Encontrar fontes · URLs candidatas")
        self.window.geometry("1000x740")
        self.window.minsize(900, 650)
        self.rows = {}
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="A consulta será enviada à Tavily. A chave fica só na memória. Limites e cobranças dependem do seu plano.",
                  wraplength=850).pack(anchor="w", pady=(0, 8))
        key_row = ttk.Frame(frame)
        key_row.pack(fill="x", pady=4)
        ttk.Label(key_row, text="Chave Tavily").pack(side="left")
        self.key = ttk.Entry(key_row, show="*")
        self.key.insert(0, pane.search_config.api_key)
        self.key.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(key_row, text="Limpar chave", command=self.clear_key).pack(side="right")
        ttk.Label(frame, text="Consulta · confira a pergunta e os recortes antes de buscar").pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=4)
        self.query = ttk.Entry(row)
        self.query.insert(0, pane.query.get())
        self.query.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Buscar fontes", command=self.search).pack(side="left", padx=8)
        self.cancel_button = ttk.Button(row, text="Cancelar busca", command=pane.cancel)
        self.cancel_button.pack(side="right")
        ttk.Label(frame, text="Uma consulta por clique, até cinco URLs institucionais. Títulos de busca não comprovam a afirmação.",
                  wraplength=850).pack(anchor="w", pady=6)
        self.historical = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Mostrar também buscas de versões anteriores", variable=self.historical,
                        command=self.refresh).pack(anchor="w")
        self.count = tk.StringVar()
        ttk.Label(frame, textvariable=self.count, wraplength=850).pack(anchor="w", pady=4)
        self.tree = pane.work.tree(frame, [("state", "Estado", 130), ("text", "Título informado pela busca", 420),
                                           ("url", "URL candidata", 380)], height=6)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Usar URL para coleta", command=self.use).pack(side="left")
        ttk.Button(row, text="Descartar candidata", command=self.discard).pack(side="left", padx=8)
        ttk.Button(row, text="Fechar", command=self.close).pack(side="right")
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=850).pack(anchor="w", pady=4)
        self.preview = ScrolledText(frame, wrap="word", height=6, font=("Segoe UI", 10))
        self.preview.pack(fill="both", expand=True)
        self.preview.configure(state="disabled")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def clear_key(self):
        self.key.delete(0, "end")
        self.pane.search_config = SearchConfig()

    def search(self):
        try:
            config = SearchConfig(self.key.get().strip()).validate()
            self.pane.search_config = config
            self.pane.start("discover", self.query.get().strip())
            self.refresh()
        except ValueError as exc:
            messagebox.showinfo("Encontrar fontes", str(exc), parent=self.window)

    def refresh(self, snapshot=None):
        if not self.window.winfo_exists():
            return
        snapshot = snapshot or self.pane.store.snapshot(self.cid)
        batches = snapshot.get("discoveries", [])
        self.rows = {batch["id"] + ":" + item["id"]: (batch, item) for batch in reversed(batches)
                     if batch["current"] or self.historical.get() for item in batch["candidates"]}
        collected = {doc["url"] for doc in snapshot["documents"]}
        self.pane.work._rows(self.tree, {key: (
            "Versão anterior" if not batch["current"] else "Descartada" if item["disposition"] == "discarded"
            else "Já coletada" if item["url"] in collected else "Candidata", item["title"], item["url"])
            for key, (batch, item) in self.rows.items()})
        self.count.set(f"{len(self.rows)} candidatas exibidas · {len(batches)} buscas registradas. Nenhum resultado é coletado automaticamente.")
        self.status.set(str(self.pane.progress.cget("text")))
        self.cancel_button.configure(state="normal" if self.pane.busy() and self.pane.task.kind == "discover" else "disabled")
        self.show_selected()

    def selected(self, require_current=False):
        selection = self.tree.selection()
        if not selection or selection[0] not in self.rows:
            return None
        batch, item = self.rows[selection[0]]
        if require_current and (not batch["current"] or item["disposition"] != "pending"):
            messagebox.showinfo("Candidata indisponível", "Escolha uma candidata atual e não descartada. Confira a pergunta antes de uma nova busca.", parent=self.window)
            return None
        return batch, item

    def show_selected(self):
        selected = self.selected()
        text = "Selecione uma candidata. Use a URL para coletar o documento e conferir seu conteúdo e contexto."
        if selected:
            batch, item = selected
            text = (f"{item['title']}\n{item['url']}\nConsulta: {batch['query']}\nBusca Tavily: {batch['searched_at']}\n"
                    + ("Motivo do descarte: " + item["discard_reason"] + "\n" if item.get("discard_reason") else "")
                    + "Título informado pelo provedor, sem comprovação do conteúdo da URL. Ainda exige coleta e conferência.")
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def use(self):
        self.refresh()
        selected = self.selected(require_current=True)
        if not selected:
            return
        if self.pane.busy():
            messagebox.showinfo("Pesquisa em andamento", "Aguarde ou cancele a tarefa antes de escolher uma fonte.", parent=self.window)
            return
        self.pane.url.delete(0, "end")
        self.pane.url.insert(0, source_url(selected[1]["url"]))
        self._close()
        self.pane.progress.configure(text="URL candidata selecionada. Clique em Coletar fonte para arquivar e conferir o documento.")

    def discard(self):
        self.refresh()
        selected = self.selected(require_current=True)
        if not selected:
            return
        reason = simpledialog.askstring("Descartar candidata", "Motivo do descarte (o registro será preservado):", parent=self.window)
        if reason:
            try:
                batch, item = selected
                self.pane.store.discard_candidate(self.cid, batch["id"], item["id"], reason)
                self.refresh()
            except ValueError as exc:
                messagebox.showinfo("Descartar candidata", str(exc), parent=self.window)

    def close(self):
        task = self.pane.task
        if self.pane.busy() and task.kind == "discover" and task.cid == self.cid:
            if not messagebox.askyesno("Cancelar busca e fechar?", "A busca ainda está em andamento. Deseja cancelá-la e fechar? Resultados já salvos serão preservados.",
                                       default=messagebox.NO, parent=self.window):
                return
            task.cancel()
        self._close()
