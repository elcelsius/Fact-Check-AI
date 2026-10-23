from dataclasses import asdict
import json
from pathlib import Path
import sys
import struct
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from factcheck.audio import AudioDevice
from factcheck.review import Debate
from factcheck.triage import validate_items
from factcheck.ui import CaptureApp


def widgets(parent, kind):
    found = []
    for child in parent.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(widgets(child, kind))
    return found


class FakeConnectionTest:
    token = "connection-test-ui"
    pending = 1
    def __init__(self, config, emit):
        self.config, self.emit = config, emit
        self.cancelled = threading.Event()
    def start(self):
        pass
    def cancel(self):
        self.cancelled.set()


class FakeExportTask:
    token = "export-test-ui"
    pending = 1
    def __init__(self, review, target, kind, include_inactive, emit):
        self.review, self.target, self.kind, self.include_inactive, self.emit = review, target, kind, include_inactive, emit
        self.cancelled = threading.Event()
    def start(self):
        pass
    def cancel(self):
        self.cancelled.set()


class FakeRecoveryTask:
    token = "recovery-test-ui"
    pending = 1
    def __init__(self, review, emit):
        self.review, self.emit = review, emit
        self.cancelled = threading.Event()
    def start(self):
        pass
    def cancel(self):
        self.cancelled.set()


@unittest.skipUnless(sys.platform == "win32", "Interface Windows")
class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.project = Path(self.directory.name)
        self.folder = self.project / "session"
        self.folder.mkdir()
        self.text = "A inflação caiu para 3,5% em 2025."
        (self.folder / "session.json").write_text(json.dumps({"debate": asdict(Debate(participants=["Ana"]))}), encoding="utf8")
        self.paragraph = {"paragraph_id": 1, "version": 1, "text": self.text, "source_text": self.text,
                          "start": 1.0, "end": 4.0, "speaker": None, "closed": True, "parts": []}
        (self.folder / "paragraphs.jsonl").write_text(json.dumps(self.paragraph), encoding="utf8")
        self.pcm = b"\x00\x10" * 6000
        with wave.open(str(self.folder / "audio.wav"), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(1000)
            wav.writeframes(self.pcm)
        self.root = tk.Tk()
        self.root.withdraw()
        with patch("factcheck.ui.loopback_devices", return_value=[AudioDevice(1, "Test", 1000, 1)]):
            self.app = CaptureApp(self.root, self.project)
        self.work = self.app.workbench
        self.work.load(self.folder)
        self.work.source_tree.selection_set("1")

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.directory.cleanup()

    def editor(self):
        self.work.edit_selected()
        window = widgets(self.root, tk.Toplevel)[0]
        editor = next(widget for widget in widgets(window, tk.Text) if str(widget["state"]) == "normal")
        return window, editor

    def test_opening_saved_session_preserves_default_unknown_speaker_and_does_not_start_ai(self):
        self.assertIsNone(self.work.runner)
        self.assertIsNone(self.work.sources[1]["speaker"])
        self.assertEqual(self.work.debate.participants, ["Ana"])
        self.assertEqual(self.work.store.claims(), [])

    def export_dialog(self):
        self.work.configure_export()
        window = widgets(self.root, tk.Toplevel)[0]
        formats = widgets(window, ttk.Combobox)[0]
        save = next(button for button in widgets(window, ttk.Button) if button["text"] == "Escolher arquivo e exportar")
        return window, formats, save

    def start_export(self):
        window, formats, save = self.export_dialog()
        formats.current(2)
        widgets(window, ttk.Checkbutton)[0].invoke()
        with patch("factcheck.workbench.filedialog.asksaveasfilename", return_value=str(self.project / "afirmacoes.csv")), \
                patch("factcheck.workbench.ExportTask", FakeExportTask):
            save.invoke()
        return window, self.work.export_task

    def test_export_dialog_cancel_does_not_start_task_or_create_directory(self):
        with patch("factcheck.workbench.ExportTask") as task:
            window, formats, save = self.export_dialog()
            next(button for button in widgets(window, ttk.Button) if button["text"] == "Cancelar").invoke()
        task.assert_not_called()
        self.assertFalse((self.folder / "exports").exists())
        self.assertIsNone(self.work.export_task)

    def test_export_uses_selected_table_and_scope_without_starting_ai(self):
        with patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            window, task = self.start_export()
        triage.assert_not_called()
        research.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(task.kind, "claims")
        self.assertTrue(task.include_inactive)
        self.assertIn(task.token, self.app.activities)
        self.assertTrue(self.work.busy())
        task.pending = 0
        task.emit("export_done", {"token": task.token, "success": True, "message": "Arquivo fictício exportado."})
        self.app.poll()
        self.assertNotIn(task.token, self.app.activities)
        self.assertIn("Arquivo fictício exportado", self.work.export_label.get())

    def test_cancelling_file_picker_keeps_export_configuration_open(self):
        window, formats, save = self.export_dialog()
        with patch("factcheck.workbench.filedialog.asksaveasfilename", return_value=""), patch("factcheck.workbench.ExportTask") as task:
            save.invoke()
        task.assert_not_called()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(list((self.folder / "exports").iterdir()), [])

    def test_export_start_failure_cleans_close_guard_and_reports_failure(self):
        window, formats, save = self.export_dialog()
        with patch("factcheck.workbench.filedialog.asksaveasfilename", return_value=str(self.project / "export.json")), \
                patch("factcheck.workbench.ExportTask", FakeExportTask), \
                patch.object(FakeExportTask, "start", side_effect=RuntimeError("Falha fictícia.")), \
                patch("factcheck.workbench.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertNotIn(FakeExportTask.token, self.app.activities)
        self.assertIsNone(self.work.export_task)
        self.assertIn("não iniciada", self.work.export_label.get())

    def test_export_cancellation_requires_confirmation_and_waits_for_completion(self):
        window, task = self.start_export()
        with patch("factcheck.workbench.messagebox.askyesno", return_value=False):
            self.work.cancel_export()
        self.assertFalse(task.cancelled.is_set())
        with patch("factcheck.workbench.messagebox.askyesno", return_value=True) as confirm:
            self.work.cancel_export()
            self.work.cancel_export()
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        self.assertTrue(task.cancelled.is_set())
        self.assertTrue(self.work.busy())
        task.pending = 0
        self.work.export_done({"token": task.token, "success": False, "message": "Exportação cancelada."})
        self.assertFalse(self.work.busy())

    def test_window_close_cancels_export_and_waits_for_done_event(self):
        window, task = self.start_export()
        with patch("factcheck.ui.messagebox.askyesno", return_value=False), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            destroy.assert_not_called()
        self.assertFalse(task.cancelled.is_set())
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertTrue(task.cancelled.is_set())
            destroy.assert_not_called()
            task.pending = 0
            task.emit("export_done", {"token": task.token, "success": False, "message": "Exportação cancelada."})
            self.app.poll()
            destroy.assert_called_once()

    def test_export_is_blocked_before_new_capture_starts_or_while_another_export_runs(self):
        self.app.session = Mock()
        self.app.folder = None
        with patch("factcheck.workbench.messagebox.showinfo") as info:
            self.work.configure_export()
        info.assert_called_once()
        self.assertEqual(widgets(self.root, tk.Toplevel), [])
        self.app.session = None
        window, task = self.start_export()
        with patch("factcheck.workbench.messagebox.showinfo") as info:
            self.work.configure_export()
        info.assert_called_once()
        self.assertEqual(widgets(self.root, tk.Toplevel), [])

    def test_saving_debate_editor_preserves_event_identity(self):
        event_id = self.work.debate.event_id
        self.work.configure_debate()
        window = widgets(self.root, tk.Toplevel)[0]
        entry = widgets(window, ttk.Entry)[0]
        entry.delete(0, "end")
        entry.insert(0, "Título corrigido")
        next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar cadastro").invoke()
        self.assertEqual(self.work.debate.event_id, event_id)
        self.assertEqual(self.work.store.debate()["event_id"], event_id)

    def test_export_can_start_during_capture_without_interrupting_audio(self):
        self.app.session = Mock()
        self.app.folder = self.folder
        window, task = self.start_export()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(task.review.folder, self.folder)
        self.app.session.cancel.assert_not_called()
        self.app.session.stop.assert_not_called()

    def add_second_paragraph(self):
        second = {**self.paragraph, "paragraph_id": 2, "start": 4.5, "end": 5.5,
                  "text": "A taxa foi de 4%.", "source_text": "A taxa foi de 4%."}
        with (self.folder / "paragraphs.jsonl").open("a", encoding="utf8") as log:
            log.write("\n" + json.dumps(second))
        self.work.store.ingest(second)
        self.work.refresh()
        self.work.source_tree.selection_set("1")
        return second

    def combine_dialog(self):
        self.work.combine_selected()
        window = widgets(self.root, tk.Toplevel)[0]
        button = next(button for button in widgets(window, ttk.Button) if button["text"] == "Combinar trechos")
        return window, button

    def combine_paragraphs(self):
        window, button = self.combine_dialog()
        for checkbox in widgets(window, ttk.Checkbutton):
            checkbox.invoke()
        button.invoke()
        return self.work.selected_source()

    def test_combination_preview_requires_authorship_check_and_cancel_preserves_sources(self):
        self.add_second_paragraph()
        window, button = self.combine_dialog()
        with patch("factcheck.workbench.messagebox.showerror") as error:
            button.invoke()
        error.assert_called_once()
        self.assertEqual(len(self.work.store.sources()), 2)
        next(button for button in widgets(window, ttk.Button) if button["text"] == "Cancelar").invoke()
        self.assertEqual(len(self.work.store.sources(include_inactive=True)), 2)

    def test_combining_closed_paragraphs_during_capture_keeps_capture_and_skips_hidden_triage(self):
        self.add_second_paragraph()
        original_file = (self.folder / "paragraphs.jsonl").read_bytes()
        self.app.session = Mock()
        self.app.folder = self.folder
        with patch.object(self.work, "analyze") as analyze:
            combined = self.combine_paragraphs()
            self.work.on_paragraph(self.paragraph)
            self.assertEqual(self.work.source_tree.get_children(), (str(combined["paragraph_id"]),))
            self.work.uncombine_selected()
        analyze.assert_not_called()
        self.assertEqual(self.work.source_tree.get_children(), ("1", "2"))
        self.app.session.cancel.assert_not_called()
        self.assertEqual((self.folder / "paragraphs.jsonl").read_bytes(), original_file)

    def test_reopening_grouped_session_preserves_original_capture_view(self):
        second = self.add_second_paragraph()
        combined = self.combine_paragraphs()
        with patch("factcheck.workbench.filedialog.askdirectory", return_value=str(self.folder)):
            self.work.open_session()
        self.assertEqual(self.work.source_tree.get_children(), (str(combined["paragraph_id"]),))
        self.assertEqual(list(self.app.paragraphs), [1, 2])
        self.assertEqual(self.app.paragraphs[1]["source_text"], self.text)
        self.assertEqual(self.app.paragraphs[2]["source_text"], second["source_text"])

    def test_combined_audio_uses_original_range_with_video_reference(self):
        self.add_second_paragraph()
        self.work.store.save_video_reference(750, 0)
        self.work.refresh()
        combined = self.combine_paragraphs()
        self.assertIn("00:12:31 → 00:12:35", self.work.time(combined))
        module = SimpleNamespace(PlaySound=Mock(), SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4)
        with patch.dict("sys.modules", {"winsound": module}):
            self.work.play_selected()
        with wave.open(str(self.project / ".cache/playback/trecho.wav"), "rb") as wav:
            self.assertEqual(wav.getnframes(), 4500)
            self.assertEqual(wav.readframes(4500), self.pcm[2000:11000])
        with wave.open(str(self.folder / "audio.wav"), "rb") as wav:
            self.assertEqual(wav.readframes(6000), self.pcm)

    def test_edited_combination_requires_text_distribution_before_undo(self):
        second = self.add_second_paragraph()
        combined = self.combine_paragraphs()
        corrected = "A inflação não caiu para 3,5% em 2025."
        self.work.store.revise(combined["paragraph_id"], 1, corrected + " " + second["text"], "Ana")
        self.work.refresh()
        self.work.uncombine_selected()
        window = widgets(self.root, tk.Toplevel)[0]
        save = next(button for button in widgets(window, ttk.Button) if button["text"] == "Descombinar preservando texto")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            save.invoke()
            widgets(window, ttk.Checkbutton)[0].invoke()
            save.invoke()
        self.assertEqual(error.call_count, 2)
        editors = [editor for editor in widgets(window, tk.Text) if str(editor["state"]) == "normal"]
        editors[0].delete("1.0", "end")
        editors[0].insert("1.0", corrected)
        save.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.source_tree.get_children(), ("1", "2"))
        self.assertEqual(self.work.store.source(1)["text"], corrected)
        self.assertEqual(self.work.store.source(1)["original"]["source_text"], self.text)
        self.assertTrue(all(source["speaker"] == "Ana" and not source["human_reviewed"] for source in self.work.sources.values()))

    def test_cancelled_reconciliation_keeps_combined_correction(self):
        self.add_second_paragraph()
        combined = self.combine_paragraphs()
        edited = self.work.store.revise(combined["paragraph_id"], 1, "Texto corrigido e preservado.", "Ana")
        self.work.refresh()
        self.work.uncombine_selected()
        window = widgets(self.root, tk.Toplevel)[0]
        next(button for button in widgets(window, ttk.Button) if button["text"] == "Cancelar").invoke()
        self.assertEqual(self.work.store.sources(), [edited])

    def test_combination_blocks_different_participants_before_opening_preview(self):
        self.add_second_paragraph()
        self.work.store.save_debate(Debate(participants=["Ana", "Bruno"]))
        for pid, speaker in [(1, "Ana"), (2, "Bruno")]:
            source = self.work.store.source(pid)
            self.work.store.revise(pid, source["revision"], source["text"], speaker)
        self.work.refresh()
        with patch("factcheck.workbench.messagebox.showinfo") as info:
            self.work.combine_selected()
        info.assert_called_once()
        self.assertEqual(widgets(self.root, tk.Toplevel), [])

    def timeline_dialog(self):
        self.work.configure_timeline()
        window = widgets(self.root, tk.Toplevel)[0]
        entry = widgets(window, ttk.Entry)[0]
        save = next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar referência")
        return window, entry, save

    def test_video_reference_updates_live_transcript_review_claim_and_dossier_on_reopen(self):
        pane, cid = self.open_dossier()
        self.app.update_paragraph(self.paragraph)
        with patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            window, entry, save = self.timeline_dialog()
            entry.insert(0, "12:30")
            save.invoke()
        triage.assert_not_called()
        research.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertIn("00:12:31 → 00:12:34", self.app.transcript.get("1.0", "end-1c"))
        self.assertEqual(self.work.source_tree.item("1", "values")[:2], ("1.0–4.0", "00:12:31 → 00:12:34"))
        self.assertIn("00:12:31 → 00:12:34", self.work.claim_detail.get("1.0", "end-1c"))
        self.assertIn("00:12:31 → 00:12:34", pane.preview.get("1.0", "end-1c"))
        self.work.load(self.folder)
        self.assertEqual(self.work.video_reference["offset_seconds"], 750)
        self.assertEqual(self.work.store.source(1)["start"], 1.0)

    def test_invalid_video_reference_stays_in_dialog_and_cancel_does_not_save(self):
        window, entry, save = self.timeline_dialog()
        entry.insert(0, "12:99")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertIsNone(self.work.store.video_reference()["offset_seconds"])
        next(button for button in widgets(window, ttk.Button) if button["text"] == "Cancelar").invoke()
        self.assertFalse(window.winfo_exists())
        self.assertIsNone(self.work.store.video_reference()["offset_seconds"])

    def test_video_reference_can_be_set_during_capture_and_removed_later(self):
        self.app.session = Mock()
        self.app.folder = self.folder
        window, entry, save = self.timeline_dialog()
        entry.insert(0, "00:00")
        save.invoke()
        self.assertEqual(self.work.video_reference["offset_seconds"], 0)
        self.assertEqual(self.work.source_tree.item("1", "values")[1], "00:00:01 → 00:00:04")
        self.app.session = None
        window, entry, save = self.timeline_dialog()
        next(button for button in widgets(window, ttk.Button) if button["text"] == "Limpar campo").invoke()
        save.invoke()
        self.assertEqual(self.work.source_tree.item("1", "values")[1], "Não definida")
        self.assertIn("referência não definida", self.work.timeline_label.get())

    def test_new_session_does_not_inherit_reference_and_old_session_keeps_its_value(self):
        self.work.store.save_video_reference(750, 0)
        self.work.refresh()
        second = self.project / "second"
        second.mkdir()
        (second / "session.json").write_text('{}', encoding="utf8")
        self.work.load(second, live=True)
        self.assertIsNone(self.work.video_reference["offset_seconds"])
        self.work.load(self.folder)
        self.assertEqual(self.work.video_reference["offset_seconds"], 750)

    def test_video_reference_is_blocked_before_capture_starts(self):
        self.app.session = Mock()
        self.app.folder = None
        with patch("factcheck.workbench.messagebox.showinfo") as info:
            self.work.configure_timeline()
        info.assert_called_once()
        self.assertEqual(widgets(self.root, tk.Toplevel), [])

    def ai_dialog(self):
        self.work.configure_ai()
        window = widgets(self.root, tk.Toplevel)[0]
        provider = widgets(window, ttk.Combobox)[0]
        key = next(widget for widget in widgets(window, ttk.Entry) if type(widget) is ttk.Entry)
        apply = next(button for button in widgets(window, ttk.Button) if button["text"] == "Aplicar configuração")
        return window, provider, key, apply

    def test_gemini_requires_explicit_selection_and_keeps_key_out_of_files(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "chave-de-teste"}):
            window, provider, key, apply = self.ai_dialog()
        self.assertEqual(provider.current(), 0)
        self.assertEqual(str(key["show"]), "*")
        self.assertEqual(self.work.ai_config.provider, "local")
        key.delete(0, "end")
        key.insert(0, "chave-propria-do-usuario")
        provider.current(1)
        apply.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.ai_config.provider, "gemini")
        self.assertEqual(self.work.ai_config.api_key, "chave-propria-do-usuario")
        self.assertIn("texto enviado ao Google", self.work.ai_label.get())
        self.assertIsNone(self.work.runner)
        for file in self.project.rglob("*"):
            if file.is_file():
                self.assertNotIn(b"chave-de-teste", file.read_bytes())
                self.assertNotIn(b"chave-propria-do-usuario", file.read_bytes())

    def test_gemini_missing_key_does_not_apply_configuration(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            window, provider, key, apply = self.ai_dialog()
        provider.current(1)
        with patch("factcheck.workbench.messagebox.showerror") as error:
            apply.invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.ai_config.provider, "local")

    def test_ai_configuration_cannot_change_during_capture(self):
        self.app.session = Mock()
        with patch("factcheck.workbench.messagebox.showinfo") as info:
            self.work.configure_ai()
        info.assert_called_once()
        self.assertEqual(widgets(self.root, tk.Toplevel), [])

    def start_connection_test(self):
        window, provider, key, apply = self.ai_dialog()
        key.delete(0, "end")
        key.insert(0, "chave-propria-ficticia")
        button = next(b for b in widgets(window, ttk.Button) if b["text"] == "Testar conexão")
        with patch("factcheck.workbench.ConnectionTest", FakeConnectionTest):
            button.invoke()
        return window, key, self.work.connection_test

    def test_testing_user_key_does_not_apply_config_or_send_debate(self):
        window, key, probe = self.start_connection_test()
        self.assertEqual(probe.config.api_key, "chave-propria-ficticia")
        self.assertEqual(self.work.ai_config.provider, "local")
        self.assertIn(probe.token, self.app.activities)
        probe.pending = 0
        self.work.connection_test_done({"token": probe.token, "success": True, "message": "Conexão validada com modelo simulado."})
        self.assertNotIn(probe.token, self.app.activities)
        self.assertIsNone(self.work.connection_test)
        self.assertEqual(self.work.ai_config.provider, "local")
        for file in self.project.rglob("*"):
            if file.is_file():
                self.assertNotIn(b"chave-propria-ficticia", file.read_bytes())

    def test_response_for_old_key_cannot_validate_new_key(self):
        window, key, probe = self.start_connection_test()
        key.delete(0, "end")
        key.insert(0, "outra-chave-ficticia")
        self.assertTrue(probe.cancelled.is_set())
        probe.pending = 0
        self.work.connection_test_done({"token": probe.token, "success": True, "message": "Conexão validada com a chave anterior."})
        texts = [self.root.getvar(str(label["textvariable"])) for label in widgets(window, ttk.Label) if str(label["textvariable"])]
        self.assertTrue(any("Chave alterada" in text for text in texts))
        self.assertFalse(any("Conexão validada" in text for text in texts))

    def test_closing_during_connection_test_requires_confirmation_and_completion(self):
        window, key, probe = self.start_connection_test()
        with patch("factcheck.ui.messagebox.askyesno", return_value=False), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertFalse(probe.cancelled.is_set())
            destroy.assert_not_called()
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertTrue(probe.cancelled.is_set())
            destroy.assert_not_called()
            probe.pending = 0
            self.app.events.put(("connection_test_done", {"token": probe.token, "success": False, "message": "Teste cancelado."}))
            self.app.poll()
            destroy.assert_called_once()

    def open_dossier(self):
        jid, source = self.work.store.begin_analysis(1)
        item = {"quote": self.text, "category": "fato", "summary": self.text, "reason": "Dado numérico a conferir.",
                "topic": "Economia", "location": None, "period": "2025", "indicator": "3,5%", "comparison": None}
        self.work.store.finish_analysis(jid, validate_items([item], self.text), {})
        self.work.refresh()
        cid = self.work.store.claims()[0]["id"]
        self.work.claim_tree.selection_set(cid)
        self.work.evidence.open_selected()
        return self.work.evidence, cid

    def test_dossier_opening_and_export_do_not_start_network_or_approve_result(self):
        with patch("factcheck.evidence_ui.ResearchTask") as task, patch("factcheck.evidence_ui.webbrowser.open") as browser:
            pane, cid = self.open_dossier()
        task.assert_not_called()
        browser.assert_not_called()
        export = self.project / "dossie.md"
        with patch("factcheck.evidence_ui.filedialog.asksaveasfilename", return_value=str(export)):
            pane.export()
        self.assertIn("PENDENTE DE REVISÃO HUMANA", export.read_text(encoding="utf8"))
        self.assertIn(self.text, export.read_text(encoding="utf8"))
        self.assertIsNone(pane.store.snapshot(cid)["decision"])

    def test_import_requires_origin_url_before_file_selection(self):
        pane, cid = self.open_dossier()
        with patch("factcheck.evidence_ui.filedialog.askopenfilename") as choose, patch("factcheck.evidence_ui.messagebox.showinfo"):
            pane.import_document()
        choose.assert_not_called()
        pane.url.insert(0, "https://ibge.gov.br/fonte")
        with patch("factcheck.evidence_ui.filedialog.askopenfilename", return_value="C:/fixture/fonte.pdf"), patch.object(pane, "start") as start:
            pane.import_document()
        start.assert_called_once_with("import", {"path": "C:/fixture/fonte.pdf", "url": "https://ibge.gov.br/fonte"})

    def test_human_dossier_decision_requires_name_and_reason_and_is_saved_separately(self):
        pane, cid = self.open_dossier()
        pane.decide()
        window = widgets(self.root, tk.Toplevel)[0]
        save = next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar decisão")
        with patch("factcheck.evidence_ui.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        name = next(widget for widget in widgets(window, ttk.Entry) if type(widget) is ttk.Entry)
        name.insert(0, "Revisor de teste")
        widgets(window, tk.Text)[0].insert("1.0", "Ainda não há fontes suficientes.")
        save.invoke()
        self.assertFalse(window.winfo_exists())
        snapshot = pane.store.snapshot(cid)
        self.assertIsNone(snapshot["preliminary"])
        self.assertEqual(snapshot["decision"]["verdict"], "inconclusiva")
        self.assertEqual(snapshot["decision"]["reviewer"], "Revisor de teste")

    def test_close_waits_for_research_process_and_retains_saved_dossier(self):
        pane, cid = self.open_dossier()
        class FakeTask:
            token = "research-test"
            pending = 1
            def __init__(task, *args):
                task.cancelled = threading.Event()
            def start(task):
                pass
            def cancel(task):
                task.cancelled.set()
        with patch("factcheck.evidence_ui.ResearchTask", FakeTask):
            pane.start("collect", "https://www.ibge.gov.br/")
        self.assertIn("research-test", self.app.activities)
        self.assertTrue(self.work.busy())
        self.work.runner = SimpleNamespace(token="triage-finished", pending=0)
        self.app.register_activity("triage-finished", "Triagem", Mock())
        self.work.triage_update({"token": "triage-finished"})
        self.assertNotIn("triage-finished", self.app.activities)
        self.assertIn("research-test", self.app.activities)
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertTrue(pane.task.cancelled.is_set())
            destroy.assert_not_called()
            pane.task.pending = 0
            self.app.events.put(("research_done", {"token": "research-test", "claim_id": cid, "message": "Cancelado."}))
            self.app.poll()
            destroy.assert_called_once()

    def test_saving_editor_changes_participant_and_text_without_modifying_original(self):
        window, editor = self.editor()
        editor.delete("1.0", "end")
        editor.insert("1.0", "A inflação caiu para 4% em 2025.")
        widgets(window, ttk.Combobox)[0].set("Ana")
        widgets(window, ttk.Checkbutton)[0].invoke()
        next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar revisão").invoke()
        source = self.work.store.source(1)
        self.assertEqual(source["revision"], 2)
        self.assertEqual(source["speaker"], "Ana")
        self.assertTrue(source["human_reviewed"])
        self.assertEqual(source["original"]["source_text"], self.text)
        self.assertIn("4%", source["text"])

    def test_unsaved_editor_requires_confirmation_before_discard(self):
        window, editor = self.editor()
        editor.insert("end", " Outra frase.")
        with patch("factcheck.workbench.messagebox.askyesno", return_value=False):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.store.source(1)["revision"], 1)
        with patch("factcheck.workbench.messagebox.askyesno", return_value=True):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())

    def test_audio_preview_reads_only_selected_range_and_preserves_recording(self):
        self.work.store.save_video_reference(750, 0)
        self.work.refresh()
        play = Mock()
        module = SimpleNamespace(PlaySound=play, SND_FILENAME=1, SND_ASYNC=2, SND_NODEFAULT=4)
        with patch.dict("sys.modules", {"winsound": module}):
            self.work.play_selected()
        preview = self.project / ".cache/playback/trecho.wav"
        with wave.open(str(preview), "rb") as wav:
            self.assertEqual(wav.getnframes(), 3000)
            self.assertEqual(wav.readframes(3000), self.pcm[2000:8000])
        with wave.open(str(self.folder / "audio.wav"), "rb") as wav:
            self.assertEqual(wav.getnframes(), 6000)
        self.assertEqual(play.call_count, 2)

    def test_audio_preview_is_blocked_during_capture_to_avoid_recapture(self):
        self.app.session = Mock()
        with patch("factcheck.workbench.messagebox.showinfo") as info:
            self.work.play_selected()
        info.assert_called_once()
        self.assertFalse((self.project / ".cache/playback/trecho.wav").exists())

    def test_reopening_incomplete_history_shows_warning_and_does_not_start_triage(self):
        reviewed = self.work.store.revise(1, 1, "Correção humana de teste.", "Ana")
        with (self.folder / "paragraphs.jsonl").open("ab") as stream:
            stream.write(b'\n{"interrompido":')
        with patch.object(self.work, "analyze") as analyze:
            self.work.load(self.folder)
        analyze.assert_not_called()
        self.assertEqual(self.work.store.source(1), reviewed)
        self.assertIn("histórico incompleto", self.work.session_label.get())
        self.assertIsNone(self.work.runner)

    def test_another_live_capture_is_rejected_before_creating_review_database(self):
        folder = self.project / "active"
        folder.mkdir()
        (folder / "session.json").write_text('{"status":"recording","owner_pid":1}', encoding="utf8")
        previous = self.work.store
        with patch("factcheck.recovery.process_alive", return_value=True), self.assertRaises(ValueError):
            self.work.load(folder)
        self.assertIs(self.work.store, previous)
        self.assertFalse((folder / "review.sqlite3").exists())

    def test_manual_closure_requires_confirmation_and_preserves_original_text(self):
        metadata = json.loads((self.folder / "session.json").read_text(encoding="utf8"))
        (self.folder / "session.json").write_text(json.dumps({**metadata, "status": "completed"}), encoding="utf8")
        self.work.store.ingest({**self.paragraph, "paragraph_id": 2, "closed": False})
        original = self.work.store.source(2)["original"]
        self.work.show_recovery()
        window = widgets(self.root, tk.Toplevel)[0]
        button = next(b for b in widgets(window, ttk.Button) if b["text"] == "Encerrar parágrafos pendentes")
        with patch("factcheck.workbench.messagebox.askyesno", return_value=False):
            button.invoke()
        self.assertFalse(self.work.store.source(2)["closed"])
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.workbench.messagebox.askyesno", return_value=True):
            button.invoke()
        self.assertTrue(self.work.store.source(2)["closed"])
        self.assertFalse(self.work.store.source(2)["human_reviewed"])
        self.assertEqual(self.work.store.source(2)["original"], original)

    def test_audio_recovery_registers_close_guard_and_waits_for_worker_completion(self):
        metadata = json.loads((self.folder / "session.json").read_text(encoding="utf8"))
        (self.folder / "session.json").write_text(json.dumps({**metadata, "status": "completed"}), encoding="utf8")
        raw = bytearray((self.folder / "audio.wav").read_bytes())
        struct.pack_into("<I", raw, 40, 2)
        (self.folder / "audio.wav").write_bytes(raw)
        self.work.show_recovery()
        window = widgets(self.root, tk.Toplevel)[0]
        button = next(b for b in widgets(window, ttk.Button) if b["text"] == "Criar cópia recuperada do áudio")
        self.assertEqual(str(button["state"]), "normal")
        with patch("factcheck.workbench.AudioRecoveryTask", FakeRecoveryTask):
            button.invoke()
        self.assertTrue(self.work.busy())
        self.assertIn("recovery-test-ui", self.app.activities)
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertTrue(self.work.recovery_task.cancelled.is_set())
            destroy.assert_not_called()
            self.work.recovery_task.pending = 0
            self.app.events.put(("recovery_done", {"token": "recovery-test-ui", "success": False, "message": "Cancelado"}))
            self.app.poll()
            destroy.assert_called_once()

    def test_automatic_analysis_waits_for_closed_paragraph_and_ignores_cancelled_tail(self):
        with patch.object(self.work, "analyze") as analyze:
            self.work.on_paragraph({**self.paragraph, "closed": False})
            self.work.on_paragraph({**self.paragraph, "end_reason": "cancelamento"})
            analyze.assert_not_called()
            self.work.on_paragraph(self.paragraph)
            analyze.assert_called_once_with(1)

    def test_triage_registers_real_close_guard_and_finishes_only_after_cancellation_event(self):
        class FakeRunner:
            token = "triage-test"
            pending = 0
            def __init__(runner, root, store, emit, config=None):
                runner.cancelled = threading.Event()
            def enqueue(runner, pid, force):
                runner.pending = 1
                return True
            def cancel(runner):
                runner.cancelled.set()

        with patch("factcheck.workbench.TriageRunner", FakeRunner):
            self.work.analyze_selected()
        self.assertIn("triage-test", self.app.activities)
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertTrue(self.work.runner.cancelled.is_set())
            destroy.assert_not_called()
            self.work.runner.pending = 0
            self.app.events.put(("triage_update", {"token": "triage-test"}))
            self.app.poll()
            destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
