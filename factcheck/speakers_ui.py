"""Vozes locais anônimas e associação explícita após ouvir os trechos."""

import tkinter as tk
from tkinter import messagebox,ttk
from tkinter.scrolledtext import ScrolledText

from .speaker_models import model_folder
from .speaker_tasks import SpeakerTask
from .speakers import SpeakerStore,STATES


class SpeakersPane:
    def __init__(self,work,notebook):
        self.work,self.app,self.root,self.notebook=work,work.app,work.root,notebook
        self.store,self.task=None,None
        self.runs,self.rows={},{ }
        self.tab=ttk.Frame(notebook,padding=12)
        notebook.add(self.tab,text="Falantes")
        ttk.Label(self.tab,text="Separe uma gravação encerrada em vozes anônimas. O modelo sugere intervalos; "
                  "ouvir e associar cada voz a um participante continua sendo uma ação humana.",wraplength=920).pack(anchor="w",pady=(0,8))
        row=ttk.Frame(self.tab)
        row.pack(fill="x",pady=4)
        ttk.Button(row,text="Preparar modelos locais",command=self.prepare).pack(side="left")
        ttk.Label(row,text="Vozes esperadas · 0 estima").pack(side="left",padx=(12,4))
        self.number=tk.StringVar(value="0")
        ttk.Spinbox(row,from_=0,to=30,textvariable=self.number,width=5).pack(side="left")
        ttk.Button(row,text="Analisar gravação",command=self.analyze).pack(side="left",padx=12)
        self.cancel_button=ttk.Button(row,text="Cancelar análise / preparação",command=self.cancel,state="disabled")
        self.cancel_button.pack(side="right")
        self.status=tk.StringVar(value="Prepare os modelos uma vez; depois, áudio e processamento permanecem locais.")
        ttk.Label(self.tab,textvariable=self.status,wraplength=920).pack(anchor="w",pady=6)
        row=ttk.Frame(self.tab)
        row.pack(fill="x",pady=4)
        ttk.Label(row,text="Análise salva").pack(side="left")
        self.run_choice=tk.StringVar()
        self.run_box=ttk.Combobox(row,textvariable=self.run_choice,state="readonly")
        self.run_box.pack(side="left",fill="x",expand=True,padx=8)
        ttk.Label(row,text="Voz").pack(side="left")
        self.voice=tk.StringVar(value="Todas")
        self.voice_box=ttk.Combobox(row,textvariable=self.voice,state="readonly",values=["Todas"],width=14)
        self.voice_box.pack(side="left",padx=8)
        ttk.Button(row,text="Atualizar lista",command=self.refresh).pack(side="right")
        self.tree=work.tree(self.tab,[("time","Captura (s)",110),("voice","Vozes detectadas",130),("state","Situação",250),
                                    ("participant","Participante atribuído",150),("text","Fala",420)],height=6)
        self.tree.configure(selectmode="extended")
        self.tree.bind("<<TreeviewSelect>>",lambda _:self.show_selected())
        row=ttk.Frame(self.tab)
        row.pack(fill="x",pady=8)
        ttk.Button(row,text="Ouvir trecho",command=self.play).pack(side="left")
        ttk.Button(row,text="Revisar fala",command=self.edit_source).pack(side="left",padx=8)
        ttk.Button(row,text="Atribuir participante à seleção",command=self.assign).pack(side="left")
        ttk.Label(row,text="Use Ctrl/Shift para selecionar vários trechos.").pack(side="right")
        self.preview=ScrolledText(self.tab,wrap="word",height=8,font=("Segoe UI",10))
        self.preview.pack(fill="both",expand=True)
        self.preview.configure(state="disabled")
        self.run_choice.trace_add("write",lambda *_:self.apply_filters())
        self.voice.trace_add("write",lambda *_:self.apply_filters())

    def busy(self):
        return bool(self.task and self.task.pending)

    def load(self,review):
        self.store=SpeakerStore(review)
        self.store.recover()
        self.run_choice.set("")
        self.voice.set("Todas")
        self.refresh()

    def refresh(self):
        if not self.store:
            return
        selected=self.selected_run()
        data=self.store.runs()
        names={"completed":"Concluída","running":"Em análise","cancelled":"Cancelada","failed":"Falhou","stale":"Áudio alterado","interrupted":"Interrompida"}
        self.runs={f"{run['started_at']} · {names[run['status']]} · {run['id'][:8]}":run for run in data}
        self.run_box.configure(values=list(self.runs))
        label=next((label for label,run in self.runs.items() if selected and run["id"]==selected["id"]),None)
        if label is None:
            label=next((label for label,run in self.runs.items() if run["status"]=="completed"),next(iter(self.runs),""))
        self.run_choice.set(label)
        run=self.selected_run()

    def selected_run(self):
        return self.runs.get(self.run_choice.get())

    def apply_filters(self):
        run=self.selected_run()
        voices=sorted({segment["voice"] for segment in (run or {}).get("segments",[])})
        self.voice_box.configure(values=["Todas",*(f"Voz {voice+1}" for voice in voices)])
        if self.voice.get() not in self.voice_box["values"]:
            self.voice.set("Todas")
        rows=self.store.candidates(run) if self.store and run and run["status"]=="completed" else []
        self.rows={str(row["source"]["paragraph_id"]):row for row in rows if self.voice.get()=="Todas" or
                   self.voice.get() in [f"Voz {voice+1}" for voice in row["voices"]]}
        self.work._rows(self.tree,{pid:(f"{row['source']['start']:.1f}–{row['source']['end']:.1f}",
            ", ".join(f"Voz {voice+1}" for voice in row["voices"]) or "Não detectada",STATES[row["state"]],
            row["source"]["speaker"] or "Não identificado",row["source"]["text"][:220]) for pid,row in self.rows.items()})
        self.show_selected()

    def selected(self):
        return [self.rows[pid] for pid in self.tree.selection() if pid in self.rows]

    def show_selected(self):
        rows=self.selected()
        run=self.selected_run()
        lines=["As vozes são rótulos desta análise, sem identidade automática. Outra execução pode usar números diferentes.",
               "Trechos com mais de uma voz detectada exigem revisão manual. Cobertura temporal não é confiança estatística."]
        if run:
            lines.extend([f"Análise: {run['id']} · {run['status']}",run.get("message","")])
        for row in rows:
            source=row["source"]
            lines.extend(["",f"Parágrafo {source['paragraph_id']} · revisão {source['revision']} · {STATES[row['state']]}",
                          f"Fala detectada: {row['speech_seconds']:.2f} s · cobertura temporal: {row['coverage']:.0%}",source["text"]])
        self.preview.configure(state="normal")
        self.preview.delete("1.0","end")
        self.preview.insert("1.0","\n".join(lines))
        self.preview.configure(state="disabled")

    def start(self,store=None,number=0):
        if self.busy() or self.app.closing:
            return
        try:
            self.task=SpeakerTask(self.app.project_root,lambda kind,data:self.app.events.put((kind,data)),store,number)
            self.app.register_activity(self.task.token,"Análise / preparação de falantes",self.task.cancel)
            self.cancel_button.configure(state="normal")
            self.status.set("Preparando tarefa local de falantes…")
            self.task.start()
        except Exception as exc:
            if self.task:
                self.task.pending=0
                self.app.activities.pop(self.task.token,None)
                if self.task.store:
                    self.task.store.fail(self.task.rid,"Não foi possível iniciar a tarefa de falantes.")
            self.cancel_button.configure(state="disabled")
            messagebox.showinfo("Falantes",str(exc) if isinstance(exc,(ValueError,OSError)) else "Não foi possível iniciar a tarefa de falantes.",parent=self.root)

    def prepare(self):
        self.start()

    def analyze(self):
        if not self.store or self.app.session:
            messagebox.showinfo("Analisar falantes","Abra uma sessão e encerre a captura antes de analisar as vozes.",parent=self.root)
            return
        try:
            number=int(self.number.get())
            if not 0<=number<=30:
                raise ValueError
        except ValueError:
            messagebox.showinfo("Vozes esperadas","Informe de zero a trinta vozes; zero estima a quantidade.",parent=self.root)
            return
        if not all((model_folder(self.app.project_root)/name).is_file() for name in ("segmentation.onnx","embedding.onnx")):
            messagebox.showinfo("Modelos locais","Clique em Preparar modelos locais antes da análise. O download não envia áudio.",parent=self.root)
            return
        self.start(self.store,number)

    def progress(self,data):
        if self.task and self.task.token==data["token"] and not self.task.cancelled.is_set():
            self.status.set(data["message"])

    def done(self,data):
        self.app.activities.pop(data["token"],None)
        if self.task and self.task.token==data["token"]:
            self.cancel_button.configure(state="disabled")
            self.status.set(data["message"])
            self.refresh()
            if data.get("success") and self.task.store is self.store and self.task.rid:
                label=next((label for label,run in self.runs.items() if run["id"]==self.task.rid),None)
                if label:
                    self.run_choice.set(label)

    def cancel(self):
        if self.busy() and messagebox.askyesno("Cancelar falantes?","Deseja cancelar a tarefa? Resultados já salvos serão preservados.",default=messagebox.NO,parent=self.root):
            self.task.cancel()

    def play(self):
        rows=self.selected()
        if len(rows)==1:
            self.work.play(rows[0]["source"])

    def edit_source(self):
        rows=self.selected()
        if len(rows)==1:
            self.work.edit(rows[0]["source"]["paragraph_id"])

    def assign(self):
        rows,run=self.selected(),self.selected_run()
        if not rows or not run or self.busy() or self.app.closing:
            return
        if any(row["state"]!="candidate" for row in rows) or len({row["voice"] for row in rows})!=1:
            messagebox.showinfo("Atribuir participante","Selecione trechos com a mesma voz única detectada. Confira falas mistas manualmente em Revisar fala.",parent=self.root)
            return
        if not self.work.debate.participants:
            messagebox.showinfo("Atribuir participante","Cadastre os participantes em Dados da transmissão antes de atribuir as falas.",parent=self.root)
            return
        store=self.store
        expected=[{"paragraph_id":row["source"]["paragraph_id"],"revision":row["source"]["revision"],"voice":row["voice"]} for row in rows]
        window,close=self.work.dialog("Atribuir participante · conferir a voz")
        window.geometry("820x700")
        window.minsize(740,640)
        frame=ttk.Frame(window,padding=16)
        frame.pack(fill="both",expand=True)
        buttons=ttk.Frame(frame)
        buttons.pack(side="bottom",fill="x",pady=(10,0))
        ttk.Label(frame,text=f"{len(rows)} trechos · Voz {rows[0]['voice']+1}. A atribuição muda a revisão da fala e exige nova triagem; "
                  "não confere o texto nem decide a veracidade.",wraplength=700).pack(anchor="w",pady=(0,8))
        text=ScrolledText(frame,height=6,wrap="word")
        text.pack(fill="both",expand=True)
        text.insert("1.0","\n\n".join(f"{row['source']['start']:.1f}–{row['source']['end']:.1f} s · {row['source']['text']}" for row in rows))
        text.configure(state="disabled")
        ttk.Label(frame,text="Participante cadastrado").pack(anchor="w",pady=(8,0))
        participant=ttk.Combobox(frame,state="readonly",values=self.work.debate.participants)
        participant.pack(fill="x",pady=5)
        heard,overwrite=tk.BooleanVar(value=False),tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text="Ouvi os trechos e confirmei que pertencem ao participante escolhido",variable=heard).pack(anchor="w",pady=4)
        ttk.Checkbutton(frame,text="Permitir substituir uma atribuição anterior diferente",variable=overwrite).pack(anchor="w",pady=4)
        ttk.Label(frame,text="Motivo obrigatório da atribuição").pack(anchor="w",pady=(8,0))
        reason=ScrolledText(frame,height=3,wrap="word")
        reason.pack(fill="x",pady=5)
        def changed():
            return bool(participant.get() or heard.get() or overwrite.get() or reason.get("1.0","end-1c"))
        def save():
            try:
                if self.store is not store:
                    raise ValueError("A sessão mudou. Reabra a atribuição.")
                updated=store.apply(run["id"],expected,participant.get(),reason.get("1.0","end-1c"),heard.get(),overwrite.get())
                self.work.refresh()
                self.status.set(f"{len(updated)} atribuições salvas. A transcrição continua pendente de conferência; solicite nova triagem.")
                close()
            except (ValueError,OSError) as exc:
                messagebox.showerror("Atribuir participante",str(exc),parent=window)
        def cancel():
            if not changed() or messagebox.askyesno("Descartar atribuição?","Há alterações não salvas. Deseja descartá-las?",default=messagebox.NO,parent=window):
                close()
        ttk.Button(buttons,text="Confirmar atribuição",command=save).pack(side="left")
        ttk.Button(buttons,text="Cancelar",command=cancel).pack(side="right")
        window.protocol("WM_DELETE_WINDOW",cancel)
