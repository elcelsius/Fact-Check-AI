"""Operação local: indicadores, limites, avaliação e cópias de segurança."""

from functools import partial
import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .evaluation import EvaluationStore
from .persistence import atomic_json
from .session_backups import FileTask, create_backup, restore_backup
from .usage import DEFAULTS, UsageStore


class OperationsPane:
    def __init__(self, work, notebook):
        self.work, self.app, self.root = work, work.app, work.root
        self.review = self.usage = self.evaluation = self.task = None
        self.task_kind = ""
        self.maximum_queue = 0
        self.last_lag = None
        self.tab = ttk.Frame(notebook, padding=14)
        notebook.add(self.tab, text="Operação e avaliação")
        self.live = tk.StringVar(value="Nenhuma captura em acompanhamento.")
        ttk.Label(self.tab, textvariable=self.live, wraplength=940).pack(anchor="w", pady=6)
        self.notice = tk.StringVar(value="Abra uma sessão para acompanhar uso, avaliar ou criar cópia de segurança.")
        ttk.Label(self.tab, textvariable=self.notice, wraplength=940).pack(anchor="w", pady=6)
        row = ttk.Frame(self.tab); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Conjunto a avaliar").pack(side="left", padx=(0, 8))
        self.partition = tk.StringVar(value="Avaliação reservada")
        ttk.Combobox(row, textvariable=self.partition, values=("Desenvolvimento", "Avaliação reservada"), state="readonly", width=24).pack(side="left")
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=6)
        for label, action in (("Atualizar indicadores", self.refresh), ("Limites e uso", self.configure),
                              ("Definir referência humana", self.reference), ("Calcular avaliação", self.evaluate)):
            ttk.Button(row, text=label, command=action).pack(side="left", padx=(0, 8))
        row = ttk.Frame(self.tab)
        row.pack(fill="x", pady=6)
        for label, action in (("Criar cópia de segurança", self.backup), ("Restaurar cópia", self.restore),
                              ("Exportar avaliação", self.export_evaluation), ("Cancelar operação", self.cancel)):
            ttk.Button(row, text=label, command=action).pack(side="left", padx=(0, 8))
        ttk.Label(self.tab, text="Cópias incluem áudio e banco da sessão; a restauração cria outra pasta. "
                  "Avaliação exige referência humana e não aprova fatos. Preços são referências informadas pelo operador.", wraplength=940).pack(anchor="w", pady=8)
        self.details = ScrolledText(self.tab, wrap="word", height=18, font=("Segoe UI", 10))
        self.details.pack(fill="both", expand=True)
        self.details.configure(state="disabled")

    def busy(self):
        return bool(self.task and self.task.pending)

    def load(self, review):
        self.review = review
        self.usage, self.evaluation = UsageStore(review), EvaluationStore(review)
        self.maximum_queue, self.last_lag = 0, None
        self.refresh()

    def live_update(self, kind, data):
        queue = data.get("queued_chunks")
        if type(queue) is int: self.maximum_queue = max(self.maximum_queue, queue)
        if "delivery_lag_seconds" in data: self.last_lag = data["delivery_lag_seconds"]
        lag = f"{self.last_lag:.1f} s" if self.last_lag is not None else "Ainda não medido"
        warning = " · Atraso elevado; confira o processamento." if self.last_lag is not None and self.last_lag >= 10 else ""
        self.live.set(f"Fila observada: {queue if queue is not None else '—'} · maior fila: {self.maximum_queue} · atraso do último trecho: {lag}{warning}")

    def refresh(self):
        if not self.review: return
        usage = self.usage.summary()
        latest = self.evaluation.latest()
        text = [f"Sessão: {self.review.folder.name}", "", "USO REGISTRADO",
                f"Desde: {usage['tracking_started_at']}", f"Tentativas de API: {usage['attempts']}/{usage['max_api_calls']} · restantes: {usage['remaining_calls']}",
                "Atenção: pelo menos 80% do limite de tentativas já foi reservado." if usage['max_api_calls'] > 0 and usage['attempts'] >= .8*usage['max_api_calls'] else "",
                f"Tokens totais informados: {usage['reported_tokens']} · créditos Tavily informados: {usage['reported_credits']}",
                f"Custo estimado: {usage['estimated_cost'] if usage['estimated_cost'] is not None else 'Indisponível'} {usage['currency']}",
                f"Tentativas sem uso ou preço informado: {usage['unpriced_or_unreported_attempts']}",
                "Saldo estimado: " + (str(usage["estimated_remaining_budget"]) if usage["estimated_remaining_budget"] is not None else "Indisponível"),
                "Orçamento de referência atingido." if usage["budget_warning"] else "", usage["limitations"], "", "AVALIAÇÃO COM REFERÊNCIA HUMANA"]
        if latest:
            metrics = latest["metrics"]
            text.extend(["Atual." if latest["current"] else "DESATUALIZADA: falas, referência ou extrações mudaram.",
                f"Conjunto: {latest['reference'].get('partition', 'evaluation')} · avaliação {latest['id']}",
                f"Parágrafos anotados: {metrics['annotated_paragraphs']}/{metrics['total_active_paragraphs']} · com triagem: {metrics['annotated_with_triage']}",
                f"Anotações declaradas cegas: {metrics['blind_references']}",
                f"Erros de palavras: {metrics['errors']}/{metrics['reference_words']} · WER: {metrics['wer']}",
                f"Correspondência literal: TP={metrics['true_positives']} FP={metrics['false_positives']} FN={metrics['false_negatives']}",
                f"Precisão literal: {metrics['literal_precision']} · cobertura literal: {metrics['literal_recall']}", *latest["limitations"]])
        else:
            text.append("Sem avaliação calculada. Não há precisão, cobertura ou WER presumidos.")
        text += ["", f"Referências humanas cadastradas: {len(self.evaluation.references())}",
                 "As decisões factuais permanecem no dossiê e não são atribuídas por estas métricas."]
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(text))
        self.details.configure(state="disabled")

    def configure(self):
        if not self.usage or self.app.closing: return
        saved = self.usage.settings()
        window, close = self.work.dialog("Limites e preços de referência · somente esta sessão")
        frame = ttk.Frame(window, padding=18); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="O limite de tentativas é aplicado antes de novos envios à API. Zero bloqueia envios de triagem e pesquisa. "
                  "Requisições já iniciadas podem terminar. A estimativa financeira não é uma fatura ou um bloqueio monetário.", wraplength=780).pack(anchor="w", pady=8)
        widgets = {}
        for key, label in (("max_api_calls", "Máximo de tentativas registradas por sessão"), ("currency", "Moeda de referência"),
                           ("budget", "Orçamento de referência · opcional"), ("gemini_per_million_tokens", "Gemini · preço médio de referência por milhão de tokens totais"),
                           ("tavily_per_credit", "Tavily · preço de referência por crédito informado")):
            ttk.Label(frame, text=label).pack(anchor="w", pady=(12, 3))
            entry = ttk.Combobox(frame, values=("USD", "BRL", "EUR"), state="readonly") if key == "currency" else ttk.Entry(frame)
            entry.pack(fill="x")
            entry.insert(0, str(saved[key])) if key != "currency" and saved[key] is not None else None
            if key == "currency": entry.set(saved[key])
            widgets[key] = entry
        ttk.Label(frame, text="Preços vazios mantêm custos indisponíveis; zero é uma referência explicitamente gratuita. "
                  "O preço médio é aplicado ao total de tokens informado, incluindo as diferenças de uso que o operador deve considerar. "
                  "Tentativas sem retorno e cancelamentos permanecem no limite; testes de conexão não pertencem à sessão.", wraplength=780).pack(anchor="w", pady=16)
        initial = tuple(entry.get() for entry in widgets.values())
        def save():
            try:
                fields = {key: entry.get().strip() or None for key, entry in widgets.items()}
                fields["max_api_calls"] = int(fields["max_api_calls"])
                self.usage.configure(saved["revision"], fields)
                self.refresh(); close()
            except (ValueError, TypeError) as exc: messagebox.showerror("Limites e uso", str(exc), parent=window)
        def cancel():
            if tuple(entry.get() for entry in widgets.values()) == initial or messagebox.askyesno("Descartar limites?", "Descartar alterações não salvas?", default=messagebox.NO, parent=window): close()
        ttk.Button(frame, text="Salvar limites", command=save).pack(side="left")
        ttk.Button(frame, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def reference(self):
        if not self.evaluation or self.app.closing: return
        sources = {f"{pid} · {source['text'][:100]}": source for pid, source in self.work.sources.items()
                   if source["closed"] and source["human_reviewed"] and not source["needs_rebase"]}
        if not sources:
            messagebox.showinfo("Referência humana", "Primeiro ouça e confira uma fala em Revisar falas, marcando a conferência da transcrição.", parent=self.root)
            return
        references = self.evaluation.references()
        window, close = self.work.dialog("Referência humana · transcrição e afirmações esperadas")
        window.geometry("860x780")
        frame = ttk.Frame(window, padding=16); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Use material conferido por uma pessoa. A anotação avalia reconhecimento e seleção de afirmações, não sua veracidade.", wraplength=800).pack(anchor="w")
        choice = ttk.Combobox(frame, state="readonly", values=list(sources)); choice.pack(fill="x", pady=8)
        text = ScrolledText(frame, height=5, wrap="word"); text.pack(fill="both", expand=True)
        ttk.Label(frame, text="Citações factuais esperadas · uma por linha, literais no texto conferido").pack(anchor="w", pady=(8, 3))
        expected = ScrolledText(frame, height=5, wrap="word"); expected.pack(fill="both", expand=True)
        none = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Conferi esta fala e não há afirmações factuais esperadas", variable=none).pack(anchor="w", pady=4)
        ttk.Label(frame, text="Anotador").pack(anchor="w")
        name = ttk.Entry(frame); name.pack(fill="x", pady=4)
        blind = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Anotei sem consultar as sugestões da IA", variable=blind).pack(anchor="w", pady=4)
        partition = ttk.Combobox(frame, state="readonly", values=("Desenvolvimento", "Avaliação reservada")); partition.set("Avaliação reservada"); partition.pack(fill="x", pady=4)
        def selected(*_):
            source = sources[choice.get()]
            text.configure(state="normal"); text.delete("1.0", "end"); text.insert("1.0", source["text"]); text.configure(state="disabled")
            saved = references.get(source["paragraph_id"], {})
            current = saved.get("source_revision") == source["revision"]
            expected.delete("1.0", "end"); expected.insert("1.0", "\n".join(saved.get("expected_facts", [])) if current else "")
            none.set(current and not saved.get("expected_facts")); name.delete(0, "end"); name.insert(0, saved.get("annotator", ""))
            blind.set(saved.get("blind", False)); partition.set("Desenvolvimento" if saved.get("partition") == "development" else "Avaliação reservada")
        choice.bind("<<ComboboxSelected>>", selected); choice.current(0); selected()
        def value(): return choice.get(), expected.get("1.0", "end-1c"), none.get(), name.get(), blind.get(), partition.get()
        initial = value()
        def save():
            try:
                source = sources[choice.get()]
                facts = [line.strip() for line in expected.get("1.0", "end-1c").splitlines() if line.strip()]
                if not facts and not none.get() or facts and none.get(): raise ValueError("Informe os fatos esperados ou confirme explicitamente que não há fatos.")
                previous = references.get(source["paragraph_id"], {})
                self.evaluation.save_reference(source["paragraph_id"], previous.get("revision", 0), source["revision"], facts, name.get(), blind.get(),
                    "development" if partition.get() == "Desenvolvimento" else "evaluation")
                self.partition.set(partition.get())
                self.refresh(); close()
            except ValueError as exc: messagebox.showerror("Referência humana", str(exc), parent=window)
        def cancel():
            if value() == initial or messagebox.askyesno("Descartar referência?", "Descartar a anotação ainda não salva?", default=messagebox.NO, parent=window): close()
        row = ttk.Frame(frame); row.pack(fill="x", pady=8)
        ttk.Button(row, text="Salvar referência", command=save).pack(side="left")
        ttk.Button(row, text="Cancelar", command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)

    def begin(self, kind, operation, arguments):
        if self.app.closing or self.app.session or self.work.busy():
            messagebox.showinfo("Operação local", "Encerre a captura e aguarde ou cancele as tarefas antes desta operação.", parent=self.root)
            return
        task = FileTask(operation, arguments, lambda event, data: self.app.events.put((event, data)))
        self.task, self.task_kind = task, kind
        self.app.register_activity(task.token, "Arquivos / avaliação local", task.cancel)
        try: task.start()
        except RuntimeError:
            task.pending = 0; self.app.activities.pop(task.token, None)
            self.notice.set("Não foi possível iniciar a operação local.")

    def backup(self):
        if not self.review: return
        target = filedialog.asksaveasfilename(parent=self.root, title="Cópia da sessão · áudio e revisão", defaultextension=".fcbak", filetypes=[("Cópia Fact-Check AI", "*.fcbak")])
        if target: self.begin("backup", create_backup, (self.review.folder, Path(target)))

    def restore(self):
        source = filedialog.askopenfilename(parent=self.root, title="Restaurar cópia em outra pasta", filetypes=[("Cópia Fact-Check AI", "*.fcbak")])
        if source: self.begin("restore", restore_backup, (Path(source), self.app.project_root/"recordings"))

    def evaluate(self):
        if self.evaluation: self.begin("evaluation", partial(self.evaluation.evaluate, partition="development" if self.partition.get() == "Desenvolvimento" else "evaluation"), ())

    def export_evaluation(self):
        if not self.evaluation: return
        latest = self.evaluation.latest()
        if not latest:
            messagebox.showinfo("Avaliação", "Calcule uma avaliação antes de exportá-la.", parent=self.root); return
        target = filedialog.asksaveasfilename(parent=self.root, title="Exportar avaliação detalhada · inclui referências e transcrições", defaultextension=".json", filetypes=[("JSON de avaliação", "*.json")])
        if not target: return
        def export(cancelled=None, progress=lambda _: None, commit_lock=None):
            path = Path(target); path.parent.mkdir(parents=True, exist_ok=True)
            with commit_lock or threading.RLock():
                if cancelled.is_set(): raise InterruptedError("Exportação cancelada.")
                atomic_json(path, latest)
            return {"path": str(path)}
        self.begin("evaluation_export", export, ())

    def cancel(self):
        if self.busy() and messagebox.askyesno("Cancelar operação?", "Cancelar e preservar arquivos anteriores e referências já salvas?", default=messagebox.NO, parent=self.root): self.task.cancel()

    def progress(self, data):
        if self.task and data["token"] == self.task.token: self.notice.set(data["message"])

    def done(self, data):
        self.app.activities.pop(data["token"], None)
        if not self.task or data["token"] != self.task.token: return
        if data["error"]:
            self.notice.set(data["error"]); return
        result = data["result"] or {}
        self.notice.set("Operação concluída. " + result.get("path", result.get("folder", "Referências e métricas preservadas.")))
        if self.task_kind == "restore" and not self.app.closing and not self.work.busy() and not any(token.startswith("editor-") for token in self.app.activities):
            self.work.load(Path(result["folder"]))
        self.refresh()
