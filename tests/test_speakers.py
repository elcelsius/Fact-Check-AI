from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import queue
import struct
import tarfile
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import wave

from factcheck.dossiers import DossierStore,render
from factcheck.exports import csv_rows,snapshot
from factcheck.review import Debate,ReviewStore
from factcheck.speaker_models import file_hash,prepare_models,read_samples
from factcheck.speaker_tasks import SpeakerTask
from factcheck.speakers import SpeakerStore,assignment_provenance,audio_info,project


TEXT="A taxa foi de 3% em 2025."


def speaker_session(folder):
    folder.mkdir(parents=True)
    debate=Debate(title="Ensaio fictício de falantes",participants=["Ana","Bia"])
    (folder/"session.json").write_text(json.dumps({"status":"completed","debate":asdict(debate)}),encoding="utf8")
    with wave.open(str(folder/"audio.wav"),"wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0"*(16000*30))
    review=ReviewStore(folder)
    for pid,start,end in [(1,0,4),(2,6,9),(3,12,15)]:
        review.ingest({"paragraph_id":pid,"version":1,"text":TEXT,"source_text":TEXT,"start":start,"end":end,"closed":True,"parts":[]})
    job,_=review.begin_analysis(1)
    review.finish_analysis(job,[{"quote":TEXT,"summary":TEXT,"category":"fato","reason":"Fala fictícia a conferir.",
        "topic":"Economia","location":None,"period":"2025","indicator":"3%","comparison":None}],{})
    cid=review.claims()[0]["id"]
    dossiers=DossierStore(review)
    dossiers.decide(cid,0,"inconclusiva","Revisor fictício","Faltam documentos.")
    return review,dossiers,cid


def result(folder,segments=None):
    return {"segments":segments if segments is not None else [
        {"start":0.2,"end":3.9,"voice":0},{"start":6.2,"end":8.9,"voice":1},{"start":12.2,"end":14.9,"voice":0}],
        "audio_sha256":file_hash(folder/"audio.wav"),"engine":{"name":"Motor fictício","method_version":1,"compute":"fixture","secret":"NAO-EXPORTAR"}}


class SpeakerStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name)
        self.review,self.dossiers,self.cid=speaker_session(self.root/"session")
        self.store=SpeakerStore(self.review)

    def tearDown(self):
        self.directory.cleanup()

    def run_result(self,segments=None):
        rid,audio=self.store.begin(2)
        self.assertTrue(self.store.finish(rid,result(self.review.folder,segments)))
        return rid

    def expected(self,pid=1,voice=0):
        return {"paragraph_id":pid,"revision":self.review.source(pid)["revision"],"voice":voice}

    def test_anonymous_analysis_preserves_names_text_claims_and_decisions(self):
        before=self.dossiers.snapshot(self.cid)
        rid=self.run_result()
        run=self.store.runs()[0]
        self.assertEqual(run["id"],rid)
        self.assertEqual(run["status"],"completed")
        self.assertEqual(before,self.dossiers.snapshot(self.cid))
        self.assertTrue(all(source["speaker"] is None for source in self.review.sources()))
        self.assertEqual([row["voice"] for row in self.store.candidates(run)],[0,1,0])
        self.assertNotIn("NAO-EXPORTAR",json.dumps(run))

    def test_project_treats_sequential_or_overlapping_voices_as_mixed_and_deduplicates_coverage(self):
        source=self.review.source(1)
        for segments in ([{"start":0,"end":2,"voice":0},{"start":2,"end":4,"voice":1}],
                         [{"start":0,"end":4,"voice":0},{"start":2,"end":3,"voice":1}]):
            projected=project(source,segments)
            self.assertEqual(projected["state"],"mixed")
            self.assertIsNone(projected["voice"])
            self.assertEqual(projected["coverage"],1)
        projected=project(source,[{"start":0,"end":4,"voice":0}]*2)
        self.assertEqual(projected["coverage"],1)
        self.assertEqual(projected["state"],"candidate")

    def test_project_requires_closed_current_source_and_enough_speech(self):
        source=self.review.source(1)
        self.assertEqual(project(source,[])["state"],"none")
        self.assertEqual(project(source,[{"start":0,"end":0.1,"voice":0}])["state"],"short")
        self.assertEqual(project({**source,"closed":False},[{"start":0,"end":4,"voice":0}])["state"],"pending")
        self.assertEqual(project({**source,"needs_rebase":True},[{"start":0,"end":4,"voice":0}])["state"],"pending")

    def test_assignment_requires_hearing_confirmation_reason_and_registered_participant(self):
        rid=self.run_result()
        for person,reason,heard in [("Ana","Motivo.",False),("Ana","",True),("Não cadastrada","Motivo.",True)]:
            with self.subTest(person=person),self.assertRaises(ValueError):
                self.store.apply(rid,[self.expected()],person,reason,heard)
        self.assertIsNone(self.review.source(1)["speaker"])
        self.assertTrue(self.dossiers.snapshot(self.cid)["decision"])

    def test_assignment_invalidates_dependent_triage_but_does_not_confirm_transcript_or_change_audio(self):
        rid=self.run_result()
        before=file_hash(self.review.folder/"audio.wav")
        self.store.apply(rid,[self.expected()],"Ana","Ouvi e identifiquei a voz.",True)
        source=self.review.source(1)
        self.assertEqual(source["speaker"],"Ana")
        self.assertEqual(source["text"],TEXT)
        self.assertFalse(source["human_reviewed"])
        self.assertEqual(source["revision"],2)
        self.assertTrue(assignment_provenance(source)["current"])
        self.assertFalse(self.dossiers.snapshot(self.cid)["valid"])
        self.assertEqual(file_hash(self.review.folder/"audio.wav"),before)
        self.assertIsNotNone(self.dossiers.snapshot(self.cid)["decision"])

    def test_multirow_assignment_is_atomic_when_later_row_changed(self):
        rid=self.run_result()
        expected=[self.expected(1),self.expected(3)]
        self.review.revise(3,1,TEXT+" Correção.",None,False)
        with self.assertRaises(ValueError):
            self.store.apply(rid,expected,"Ana","Conferência fictícia.",True)
        self.assertIsNone(self.review.source(1)["speaker"])
        self.assertEqual(self.review.source(1)["revision"],1)
        self.assertTrue(self.dossiers.snapshot(self.cid)["valid"])

    def test_replacing_previous_name_requires_explicit_option_and_same_name_is_noop(self):
        rid=self.run_result()
        self.review.revise(1,1,TEXT,"Bia",True)
        with self.assertRaisesRegex(ValueError,"atribuição anterior"):
            self.store.apply(rid,[self.expected()],"Ana","Corrigir participante.",True)
        self.store.apply(rid,[self.expected()],"Ana","Corrigir após ouvir.",True,True)
        before=self.review.source(1)
        self.assertFalse(before["human_reviewed"])
        self.assertEqual(self.store.apply(rid,[self.expected()],"Ana","Mesma atribuição.",True),[])
        self.assertEqual(self.review.source(1),before)

    def test_mixed_source_cannot_be_assigned_even_with_old_single_voice_selection(self):
        rid=self.run_result([{"start":0,"end":2,"voice":0},{"start":2,"end":4,"voice":1}])
        with self.assertRaises(ValueError):
            self.store.apply(rid,[self.expected()],"Ana","Seleção antiga.",True)

    def test_source_beyond_available_audio_is_not_eligible(self):
        rid=self.run_result([{"start":28,"end":30,"voice":0}])
        self.review.ingest({"paragraph_id":4,"version":1,"source_text":TEXT,"text":TEXT,"start":28,"end":31,"closed":True,"parts":[]})
        row=next(row for row in self.store.candidates(self.store.runs()[0]) if row["source"]["paragraph_id"]==4)
        self.assertEqual(row["state"],"short")
        with self.assertRaises(ValueError):
            self.store.apply(rid,[self.expected(4)],"Ana","Áudio incompleto.",True)

    def test_audio_change_rejects_assignment_and_late_result(self):
        rid=self.run_result()
        pending,_=self.store.begin()
        with (self.review.folder/"audio.wav").open("r+b") as stream:
            stream.seek(44)
            stream.write(b"\x01\x00")
        with self.assertRaisesRegex(ValueError,"áudio mudou"):
            self.store.apply(rid,[self.expected()],"Ana","Arquivo alterado.",True)
        self.assertFalse(self.store.finish(pending,result(self.review.folder)))
        self.assertEqual(self.store.runs()[0]["status"],"stale")

    def test_cancelled_run_cannot_accept_late_results_and_running_job_is_exclusive(self):
        rid,_=self.store.begin()
        with self.assertRaises(ValueError):
            self.store.begin()
        self.store.fail(rid,"Cancelamento fictício.",True)
        self.assertFalse(self.store.finish(rid,result(self.review.folder)))
        self.assertEqual(self.store.runs()[0]["status"],"cancelled")

    def test_recovery_marks_dead_owner_interrupted_without_restarting_work(self):
        self.store.begin()
        with patch("factcheck.speakers.process_alive",return_value=False):
            SpeakerStore(self.review).recover()
        self.assertEqual(self.store.runs()[0]["status"],"interrupted")
        self.assertTrue(all(source["speaker"] is None for source in self.review.sources()))

    def test_invalid_intervals_and_nonfinite_results_are_not_persisted(self):
        for invalid in ([{"start":float('nan'),"end":1,"voice":0}],[{"start":30.05,"end":30.1,"voice":0}],
                        [{"start":0,"end":1,"voice":True}],[{"start":0,"end":31,"voice":0}]):
            rid,_=self.store.begin()
            with self.assertRaises(ValueError):
                self.store.finish(rid,result(self.review.folder,invalid))
            self.store.fail(rid,"Resultado inválido no ensaio.")
        self.assertTrue(all(run["status"]=="failed" for run in self.store.runs()))

    def test_exports_include_only_confirmed_assignment_not_all_anonymous_runs(self):
        rid=self.run_result()
        self.assertNotIn("speaker_assignment",snapshot(self.review)["paragraphs"][0])
        self.store.apply(rid,[self.expected()],"Ana","Ouvi a voz fictícia.",True)
        data=snapshot(self.review)
        source=data["paragraphs"][0]
        self.assertEqual(source["speaker_assignment"]["run_id"],rid)
        self.assertTrue(source["speaker_assignment"]["current"])
        self.assertNotIn("speaker_runs",data)
        row=next(csv_rows(data,"paragraphs"))
        self.assertEqual(row["falante_voz_id"],0)
        self.assertEqual(row["falante_atribuicao_atual"],"sim")
        self.assertNotIn(str(self.review.folder),json.dumps(data))

    def test_new_triage_records_confirmed_origin_and_later_manual_revision_clears_it(self):
        rid=self.run_result()
        self.store.apply(rid,[self.expected()],"Ana","Ouvi a voz.",True)
        old=self.review.claims()[0]
        job,_=self.review.begin_analysis(1)
        self.review.finish_analysis(job,[{key:old.get(key) for key in ("quote","summary","category","reason","topic","location","period","indicator","comparison")}],{})
        claim=next(claim for claim in self.review.claims() if claim["analysis_id"]==job)
        self.assertEqual(claim["speaker_assignment"]["run_id"],rid)
        self.assertEqual(claim["speaker"],"Ana")
        self.assertIn("Atribuição assistida",render(self.dossiers.snapshot(claim["id"])))
        self.review.revise(1,2,TEXT,"Bia",False)
        self.assertNotIn("speaker_assignment",self.review.source(1))
        historic=next(item for item in snapshot(self.review,True)["claims"] if item["claim_id"]==claim["id"])
        self.assertFalse(historic["speaker_assignment"]["current"])

    def test_task_cancel_and_start_failure_leave_no_late_assignment(self):
        emitted=[]
        task=SpeakerTask(self.root,lambda kind,data:emitted.append((kind,data)),self.store)
        task.cancel()
        task._run()
        self.assertEqual(self.store.runs()[0]["status"],"cancelled")
        self.assertEqual(task.pending,0)
        self.assertFalse(emitted[-1][1]["success"])
        task=SpeakerTask(self.root,lambda kind,data:emitted.append((kind,data)),self.store)
        context=SimpleNamespace(Queue=queue.Queue,Event=threading.Event,Process=Mock(side_effect=RuntimeError("Falha simulada")))
        with patch("factcheck.speaker_tasks.mp.get_context",return_value=context):
            task._run()
        self.assertEqual(self.store.runs()[0]["status"],"failed")

    def test_resampling_real_pcm_to_mono_16khz_preserves_original(self):
        path=self.root/"stereo.wav"
        with wave.open(str(path),"wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(struct.pack("<hh",1000,-1000)*48000)
        before=file_hash(path)
        samples=read_samples(path)
        self.assertEqual(len(samples),16000)
        self.assertLess(float(abs(samples).max()),1e-5)
        self.assertEqual(file_hash(path),before)


class SpeakerModelPreparationTests(unittest.TestCase):
    def test_download_is_explicit_pinned_and_extracts_only_fixed_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            output=BytesIO()
            with tarfile.open(fileobj=output,mode="w:bz2") as archive:
                for name,body in [("model.onnx",b"fake-segmentation"),("LICENSE",b"license"),("../../outside.txt",b"Do not extract")]:
                    info=tarfile.TarInfo("sherpa-onnx-pyannote-segmentation-3-0/"+name)
                    info.size=len(body)
                    archive.addfile(info,BytesIO(body))
            bodies={"seg":output.getvalue(),"emb":b"fake-embedding"}
            segmentation={"id":"seg","file":"segmentation.tar.bz2","size":len(bodies['seg']),"sha256":sha256(bodies['seg']).hexdigest()}
            embedding={"id":"emb","file":"embedding.onnx","size":len(bodies['emb']),"sha256":sha256(bodies['emb']).hexdigest()}
            hashes={"segmentation.onnx":sha256(b"fake-segmentation").hexdigest(),"embedding.onnx":embedding["sha256"]}
            fetch=Mock(side_effect=lambda asset,target,cancel:target.write_bytes(bodies[asset]))
            with patch("factcheck.speaker_models.SEGMENTATION",segmentation),patch("factcheck.speaker_models.EMBEDDING",embedding),patch("factcheck.speaker_models.MODEL_HASHES",hashes):
                prepare_models(root,fetch=fetch)
                self.assertEqual(fetch.call_count,2)
                self.assertFalse((root/"outside.txt").exists())
                fetch.reset_mock()
                prepare_models(root,fetch=fetch)
                fetch.assert_not_called()
                (root/"models/offline-speakers/embedding.onnx").write_bytes(b"invalid")
                with self.assertRaises(ValueError):
                    prepare_models(root,fetch=lambda asset,target,cancel:target.write_bytes(b"wrong content"))
                self.assertEqual((root/"models/offline-speakers/segmentation.onnx").read_bytes(),b"fake-segmentation")


if __name__=="__main__":
    unittest.main()
