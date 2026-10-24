"""Vozes anônimas por sessão e atribuição humana com controle de versões."""

from hashlib import sha256
import json
import math
from pathlib import Path
import wave
import uuid

from .grouping import active
from .recovery import SAFE_STATES, capture_state, playback_path
from .review import now, process_alive


STATES = {"candidate": "Voz única detectada · conferir", "mixed": "Vozes diferentes · conferir manualmente",
          "short": "Pouca fala detectada", "none": "Sem fala detectada", "pending": "Origem pendente ou parágrafo aberto"}


def audio_info(folder):
    folder = Path(folder).resolve()
    if capture_state(folder)[0] not in SAFE_STATES:
        raise ValueError("Encerre a captura e confirme o estado da sessão antes de analisar falantes.")
    path = playback_path(folder).resolve()
    if not path.is_relative_to(folder):
        raise ValueError("O áudio precisa pertencer à pasta da sessão.")
    with path.open("rb") as stream:
        stamp = path.stat()
        header = stream.read(44)
    with wave.open(str(path), "rb") as wav:
        duration = wav.getnframes()/wav.getframerate()
        if wav.getsampwidth()!=2 or not 0 < duration <= 3*3600:
            raise ValueError("A análise exige áudio WAV PCM16 disponível, de até três horas.")
        rate, channels = wav.getframerate(), wav.getnchannels()
    token = sha256(f"{stamp.st_size}:{stamp.st_mtime_ns}:{header.hex()}".encode()).hexdigest()
    return {"file": path.relative_to(folder).as_posix(), "token": token, "duration": duration,
            "sample_rate": rate, "channels": channels, "bytes": stamp.st_size}


def _union(intervals):
    result = []
    for start, end in sorted(intervals):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return sum(end-start for start, end in result)


def project(source, segments):
    start, end = source["start"], source["end"]
    voices = {}
    for segment in segments:
        left, right = max(start, segment["start"]), min(end, segment["end"])
        if right > left:
            voices.setdefault(segment["voice"], []).append((left, right))
    speech = _union([interval for intervals in voices.values() for interval in intervals])
    duration = max(0, end-start)
    coverage = speech/duration if duration else 0
    state = ("pending" if not source["closed"] or source["needs_rebase"] else "mixed" if len(voices)>1 else
             "none" if not voices else "short" if speech<0.25 or coverage<0.25 else "candidate")
    return {"state": state, "voice": next(iter(voices)) if state=="candidate" else None,
            "coverage": round(coverage, 4), "speech_seconds": round(speech, 3), "voices": sorted(voices)}


def assignment_provenance(source):
    assignment = source.get("speaker_assignment")
    if not assignment:
        return None
    return {**assignment, "current": bool(active(source) and assignment["source_revision"] == source["revision"]
                                          and assignment["participant"] == source["speaker"])}


class SpeakerStore:
    def __init__(self, review):
        self.review = review
        with review.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS speaker_runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL)")

    def runs(self):
        with self.review.connection() as db:
            return [{"id": rid, "status": status, **json.loads(payload)} for rid, status, payload in
                    db.execute("SELECT id,status,payload FROM speaker_runs ORDER BY rowid DESC")]

    def recover(self):
        with self.review.connection() as db:
            for rid, payload in db.execute("SELECT id,payload FROM speaker_runs WHERE status='running'").fetchall():
                data = json.loads(payload)
                if not process_alive(data.get("owner_pid", 0)):
                    data.update(ended_at=now(), message="Análise interrompida; nenhuma atribuição foi aplicada automaticamente.")
                    db.execute("UPDATE speaker_runs SET status='interrupted',payload=? WHERE id=?", (json.dumps(data), rid))
                    self.review._audit(db, "speaker_analysis_interrupted", {"run_id": rid})

    def begin(self, num_speakers=0):
        import os
        if type(num_speakers) is not int or not 0 <= num_speakers <= 30:
            raise ValueError("Informe de zero a trinta vozes; zero estima a quantidade.")
        audio = audio_info(self.review.folder)
        with self.review.connection() as db:
            if db.execute("SELECT 1 FROM speaker_runs WHERE status='running'").fetchone():
                raise ValueError("Já existe análise de falantes em andamento nesta sessão.")
            rid = uuid.uuid4().hex
            data = {"started_at": now(), "owner_pid": os.getpid(), "audio": audio, "num_speakers_requested": num_speakers}
            db.execute("INSERT INTO speaker_runs VALUES (?,'running',?)", (rid, json.dumps(data)))
            self.review._audit(db, "speaker_analysis_started", {"run_id": rid, **data})
            return rid, audio

    def finish(self, rid, result):
        audio = audio_info(self.review.folder)
        with self.review.connection() as db:
            row = db.execute("SELECT status,payload FROM speaker_runs WHERE id=?", (rid,)).fetchone()
            if not row or row[0] != "running":
                return False
            data = json.loads(row[1])
            if data["audio"]["token"] != audio["token"]:
                data.update(message="O áudio mudou durante a análise; resultado não aplicado.", ended_at=now())
                db.execute("UPDATE speaker_runs SET status='stale',payload=? WHERE id=?", (json.dumps(data),rid))
                return False
            segments = result.get("segments")
            if not isinstance(segments, list) or len(segments)>100000:
                raise ValueError("Resultado de falantes inválido.")
            checked = []
            for segment in segments:
                if (not isinstance(segment, dict) or set(segment)!={"start","end","voice"}
                        or any(type(segment.get(key)) not in (int,float) or not math.isfinite(segment[key]) for key in ("start","end"))
                        or not 0 <= segment["start"] < min(segment["end"], audio["duration"])
                        or segment["end"] > audio["duration"]+0.15
                        or type(segment["voice"]) is not int or not 0 <= segment["voice"] <= 999):
                    raise ValueError("Intervalo de voz inválido.")
                checked.append({**segment, "end": min(segment["end"],audio["duration"])})
            digest = result.get("audio_sha256")
            if not isinstance(digest,str) or len(digest)!=64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("Identificação do áudio ausente.")
            engine = result.get("engine") or {}
            engine = {key: engine[key] for key in ("name","method_version","compute","segmentation","embedding","model_hashes","version",
                                                 "num_speakers_requested","clustering_threshold","seconds") if key in engine}
            data.update(ended_at=now(), segments=sorted(checked,key=lambda item:(item["start"],item["end"],item["voice"])),
                        engine=engine, audio={**audio,"sha256":digest})
            data["result_sha256"] = sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
            db.execute("UPDATE speaker_runs SET status='completed',payload=? WHERE id=?",(json.dumps(data,ensure_ascii=False),rid))
            self.review._audit(db,"speaker_analysis_completed",{"run_id":rid,"result_sha256":data["result_sha256"],"segments":len(checked)})
            return True

    def fail(self, rid, message, cancelled=False):
        with self.review.connection() as db:
            row = db.execute("SELECT status,payload FROM speaker_runs WHERE id=?",(rid,)).fetchone()
            if row and row[0]=="running":
                data={**json.loads(row[1]),"ended_at":now(),"message":message}
                db.execute("UPDATE speaker_runs SET status=?,payload=? WHERE id=?",("cancelled" if cancelled else "failed",json.dumps(data),rid))

    def candidates(self, run):
        rows=[]
        for source in self.review.sources():
            row={"source":source,**project(source,run["segments"])}
            if source["end"] > run["audio"]["duration"]+0.001:
                row.update(state="short",voice=None)
            rows.append(row)
        return rows

    def apply(self, rid, expected, participant, reason, heard=False, overwrite=False):
        if (not isinstance(reason,str) or not reason.strip() or len(reason)>2000 or heard is not True
                or type(overwrite) is not bool or not isinstance(expected,list) or not 1<=len(expected)<=500):
            raise ValueError("Selecione até 500 trechos, informe o motivo e confirme que ouviu e identificou o participante.")
        if any(not isinstance(item,dict) or set(item)!={"paragraph_id","revision","voice"} or
               any(type(item.get(key)) is not int for key in item) for item in expected):
            raise ValueError("Seleção de falas inválida.")
        if len({item["paragraph_id"] for item in expected})!=len(expected):
            raise ValueError("Há trechos repetidos na seleção.")
        if len({item["voice"] for item in expected})!=1:
            raise ValueError("Escolha trechos da mesma voz nesta atribuição.")
        audio=audio_info(self.review.folder)
        with self.review.connection() as db:
            row=db.execute("SELECT status,payload FROM speaker_runs WHERE id=?",(rid,)).fetchone()
            if not row or row[0]!="completed":
                raise ValueError("Escolha uma análise concluída de falantes.")
            run=json.loads(row[1])
            if run["audio"]["token"]!=audio["token"]:
                raise ValueError("O áudio mudou. Faça nova análise antes de atribuir participantes.")
            debate=json.loads(db.execute("SELECT payload FROM debate WHERE id=1").fetchone()[0])
            if not isinstance(participant,str) or participant not in debate["participants"]:
                raise ValueError("Escolha um participante cadastrado nos dados da transmissão.")
            updated=[]
            for item in expected:
                row=db.execute("SELECT payload FROM paragraphs WHERE id=?",(item["paragraph_id"],)).fetchone()
                source=json.loads(row[0]) if row else None
                if not source or not active(source) or source["revision"]!=item["revision"]:
                    raise ValueError("Uma fala mudou ou foi substituída. Atualize e confira a seleção.")
                match=project(source,run["segments"])
                if match["state"]!="candidate" or match["voice"]!=item["voice"] or source["end"]>run["audio"]["duration"]+0.001:
                    raise ValueError("Há vozes diferentes ou áudio insuficiente em um trecho. Revise essa fala manualmente.")
                if source["speaker"] and source["speaker"]!=participant and not overwrite:
                    raise ValueError("Há atribuição anterior diferente. Confira e autorize explicitamente a substituição.")
                if source["speaker"]==participant:
                    continue
                previous=json.loads(json.dumps(source))
                source.update(revision=source["revision"]+1,speaker=participant,human_reviewed=False,edited=True)
                source["speaker_assignment"]={"run_id":rid,"voice":item["voice"],"participant":participant,"assigned_at":now(),
                    "reason":reason.strip(),"source_revision":source["revision"],"audio_sha256":run["audio"]["sha256"],
                    "result_sha256":run["result_sha256"],"engine":run["engine"],"heard_confirmation":True}
                self.review._save(db,source)
                self.review._invalidate(db,source["paragraph_id"])
                self.review._audit(db,"speaker_assigned",{"previous":previous,"current":source})
                updated.append(source)
            return updated
