"""Pesquisa dos casos visíveis, iniciada e limitada pelo operador."""

import tkinter as tk
import sqlite3
from tkinter import messagebox, ttk

from .discovery import SearchConfig
from .research_queue import QueueConfig, ResearchQueue


def open_queue(work):
    if not work.store or work.app.closing:
        return
    if work.batch and work.batch.pending:
        messagebox.showinfo("Pesquisa em fila", "Já existe uma fila ativa. Aguarde ou cancele a fila atual.", parent=work.root)
        return
    if work.evidence.busy():
        messagebox.showinfo("Pesquisa em fila", "Aguarde ou cancele a pesquisa atual antes de iniciar a fila.", parent=work.root)
        return
    candidates = [claim for claim in work.visible_claims.values() if claim["category"] == "fato"][:200]
    if not candidates:
        messagebox.showinfo("Pesquisa em fila", "Aplique os filtros e deixe visíveis as afirmações factuais que deseja pesquisar.", parent=work.root)
        return
    window, close = work.dialog("Pesquisa em fila · limites e envio opcional às APIs")
    work.batch_window = window
    window.geometry("930x740")
    window.minsize(800, 680)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Somente casos atuais, sem decisão humana e com plano pesquisável conferido serão executados. "
              "A prioridade atual é conferida entre casos; a tarefa em andamento não é interrompida. Nenhum resultado é aprovado ou publicado.", wraplength=870).pack(anchor="w")
    tree = ttk.Treeview(frame, columns=("summary", "plan", "urls"), show="headings", height=7, selectmode="extended")
    for key, label, width in (("summary", "Afirmação visível", 570), ("plan", "Plano", 200), ("urls", "URLs", 50)):
        tree.heading(key, text=label)
        tree.column(key, width=width)
    eligible = []
    for claim in candidates:
        data = work.evidence.store.snapshot(claim["id"])
        plan = data.get("plan") or {}
        ready = data["valid"] and not data["decision"] and plan.get("scope") == "pesquisavel" and plan.get("origin") == "operator_input" and not plan.get("needs_review")
        tree.insert("", "end", iid=claim["id"], values=(claim["summary"][:170], "Conferido" if ready else "A conferir / histórico", len(plan.get("candidate_urls", []))))
        if ready: eligible.append(claim["id"])
    tree.selection_set(eligible)
    tree.pack(fill="both", expand=True, pady=8)
    limits = {}
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=6)
    for key, label, value, maximum in (("cases", "Casos", 10, 20), ("docs", "Fontes por caso", 2, 6),
                                       ("tasks", "Tarefas no total", 30, 100), ("minutes", "Minutos no total", 15, 60)):
        cell = ttk.Frame(row)
        cell.pack(side="left", padx=(0, 20))
        ttk.Label(cell, text=label).pack(anchor="w")
        limits[key] = tk.StringVar(value=str(value))
        ttk.Spinbox(cell, from_=1, to=maximum, textvariable=limits[key], width=8).pack(anchor="w")
    search = tk.BooleanVar(value=False)
    analyze = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text="Buscar novas URLs na Tavily · envia a pergunta e os recortes do plano", variable=search).pack(anchor="w", pady=4)
    ttk.Label(frame, text="Chave Tavily opcional · somente na memória").pack(anchor="w")
    key = ttk.Entry(frame, show="•")
    key.insert(0, work.evidence.search_config.api_key)
    key.pack(fill="x", pady=4)
    ttk.Checkbutton(frame, text="Pedir análise preliminar ao Gemini · envia fala e trechos das fontes; exige chave em Configurar IA", variable=analyze).pack(anchor="w", pady=4)
    ttk.Label(frame, text="Sem busca, serão usadas as URLs candidatas do plano. Fontes coletadas permanecem sem validação. "
              "Alterações da fala, plano ou uma decisão humana retiram o caso da fila. Falha de API interrompe novos envios.", wraplength=870).pack(anchor="w", pady=6)
    progress = ttk.Label(frame, text="Selecione os casos e confira os limites antes de começar.", wraplength=870)
    progress.pack(anchor="w", pady=4)
    work.batch_progress = progress
    def start():
        if work.batch and work.batch.pending: return
        batch = None
        try:
            if work.evidence.busy():
                raise ValueError("Aguarde ou cancele a pesquisa iniciada enquanto esta janela estava aberta.")
            config = QueueConfig(int(limits["cases"].get()), int(limits["docs"].get()), int(limits["tasks"].get()),
                                 int(limits["minutes"].get())*60, search.get(), analyze.get())
            selected = list(tree.selection())
            search_config = SearchConfig(key.get()) if search.get() else work.evidence.search_config
            batch = ResearchQueue(work.evidence.store, selected, config, lambda kind, data: work.app.events.put((kind, data)), search_config, work.ai_config)
            work.batch = batch
            if search.get(): work.evidence.search_config = search_config
            work.app.register_activity(batch.token, "Pesquisa em fila", batch.cancel)
            batch.start()
            progress.configure(text="Fila iniciada. Fontes serão coletadas; revisão humana permanece pendente.")
        except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
            if batch:
                batch.pending = 0
                work.app.activities.pop(batch.token, None)
                try:
                    batch.audit.save(batch.bid, "failed", {**batch.data, "message": "Não foi possível iniciar a fila."})
                except (OSError, sqlite3.Error):
                    progress.configure(text="Falha ao registrar a fila. Confira o armazenamento e reabra o aplicativo antes de tentar outra pesquisa.")
            messagebox.showerror("Pesquisa em fila", str(exc), parent=window)
    def cancel():
        if work.batch and work.batch.pending and messagebox.askyesno("Cancelar fila?", "Cancelar as tarefas pendentes e preservar os resultados já salvos?", default=messagebox.NO, parent=window):
            work.batch.cancel()
    def finish():
        if work.batch and work.batch.pending:
            if not messagebox.askyesno("Cancelar fila e fechar?", "Há pesquisa em andamento. Deseja cancelar a fila e fechar esta janela?", default=messagebox.NO, parent=window): return
            work.batch.cancel()
        close()
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=8)
    ttk.Button(row, text="Começar pesquisas", command=start).pack(side="left")
    ttk.Button(row, text="Cancelar fila", command=cancel).pack(side="left", padx=8)
    ttk.Button(row, text="Fechar", command=finish).pack(side="right")
    window.protocol("WM_DELETE_WINDOW", finish)
