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
from factcheck.exports import FORMATS
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


class FakeDiscoveryTask:
    token = "discovery-test-ui"
    pending = 1
    def __init__(self, store, cid, kind, argument, config, emit):
        self.cid, self.kind, self.argument, self.config = cid, kind, argument, config
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

    def test_rehearsal_report_selects_text_suffix_and_disables_historical_scope_without_running_ai(self):
        window, formats, save = self.export_dialog()
        formats.current(list(FORMATS).index("report_txt"))
        formats.event_generate("<<ComboboxSelected>>")
        history = next(widget for widget in widgets(window, ttk.Checkbutton) if str(widget["text"]).startswith("Incluir itens"))
        self.assertEqual(str(history["state"]), "disabled")
        with patch("factcheck.workbench.filedialog.asksaveasfilename", return_value=str(self.project / "relatorio.txt")) as picker, \
                patch("factcheck.workbench.ExportTask", FakeExportTask), \
                patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            save.invoke()
        self.assertEqual(picker.call_args.kwargs["defaultextension"], ".txt")
        self.assertEqual(self.work.export_task.kind, "report_txt")
        triage.assert_not_called()
        research.assert_not_called()
        self.assertTrue(self.work.busy())

    def test_rehearsal_report_is_blocked_during_capture_before_file_selection(self):
        self.app.session = Mock()
        self.app.folder = self.folder
        window, formats, save = self.export_dialog()
        formats.current(list(FORMATS).index("report_json"))
        with patch("factcheck.workbench.filedialog.asksaveasfilename") as picker, \
                patch("factcheck.workbench.messagebox.showerror") as error, patch("factcheck.workbench.ExportTask") as task:
            save.invoke()
        picker.assert_not_called()
        task.assert_not_called()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())

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

    def library_entry(self, **changes):
        from tests.test_source_library import fields
        library = self.work.library
        self.assertTrue(library.ensure_store())
        entry = library.store.save(fields(**changes), "Preparar referência para o ensaio.")
        library.refresh()
        library.tree.selection_set(entry["id"])
        library.show_selected()
        return library, entry

    def test_library_can_be_used_without_an_open_dossier_or_api_key(self):
        library, entry = self.library_entry()
        self.assertIsNone(self.work.evidence.cid)
        self.assertIsNone(library.target)
        self.assertEqual(str(library.use_button["state"]), "disabled")
        self.assertEqual(library.store.path, self.project / "library" / "sources.sqlite3")
        self.assertEqual(self.work.ai_config.provider, "local")
        self.assertIn("Metodologia informada", library.preview.get("1.0", "end"))

    def test_library_editor_registers_metadata_without_starting_research(self):
        library = self.work.library
        library.edit()
        window = widgets(self.root, tk.Toplevel)[0]
        entries = widgets(window, ttk.Entry)
        for widget, value in zip(entries, ["Indicador fictício", "https://ibge.gov.br/ensaio-ui", "Instituição fictícia", "Economia; Preços", "Mensal"]):
            widget.insert(0, value)
        widgets(window, tk.Text)[0].insert("1.0", "Preparar referência para o ensaio.")
        with patch("factcheck.evidence_ui.ResearchTask") as research, patch("factcheck.workbench.TriageRunner") as triage:
            next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar referência").invoke()
        research.assert_not_called()
        triage.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(len(library.store.entries()), 1)
        self.assertEqual(library.store.entries()[0]["topics"], ["Economia", "Preços"])
        self.assertEqual(self.work.store.claims(), [])

    def test_library_selection_records_a_candidate_and_only_prepares_the_url(self):
        pane, cid = self.open_dossier()
        library, entry = self.library_entry()
        library.open_for_case()
        library.tree.selection_set(entry["id"])
        with patch("factcheck.evidence_ui.ResearchTask") as research:
            library.use()
        research.assert_not_called()
        self.assertEqual(pane.url.get(), entry["url"])
        dossier = pane.store.snapshot(cid)
        self.assertEqual(dossier["documents"], [])
        self.assertEqual(len(dossier["library_references"]), 1)
        self.assertEqual(self.app.notebook.select(), str(pane.tab))

    def test_old_library_target_is_rejected_after_plan_changes(self):
        pane, cid = self.open_dossier()
        library, entry = self.library_entry()
        library.open_for_case()
        pane.store.save_plan(cid, 0, {"question": "Qual o indicador nacional?", "scope": "pesquisavel", "period": "2025",
            "territory": "Brasil", "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        with patch("factcheck.library_ui.messagebox.showinfo") as info:
            library.use()
        info.assert_called_once()
        self.assertEqual(pane.url.get(), "")
        self.assertEqual(pane.store.snapshot(cid)["library_references"], [])

    def test_changed_or_archived_catalog_entry_cannot_be_used_from_stale_ui(self):
        from tests.test_source_library import fields
        pane, cid = self.open_dossier()
        library, entry = self.library_entry()
        library.open_for_case()
        library.store.save(fields(notes="Nova versão do cadastro."), "Atualizar observação.", entry["id"], 1)
        with patch("factcheck.library_ui.messagebox.showinfo") as info:
            library.use()
        info.assert_called_once()
        self.assertEqual(pane.store.snapshot(cid)["library_references"], [])
        library.store.set_archived(entry["id"], 2, True, "Fora da pauta.")
        library.refresh()
        self.assertEqual(library.tree.get_children(), ())
        library.archived.set(True)
        library.tree.selection_set(entry["id"])
        library.show_selected()
        self.assertEqual(str(library.use_button["state"]), "disabled")

    def test_library_filters_use_loaded_data_and_keep_a_topic_after_last_item_changes(self):
        from tests.test_source_library import fields
        library, entry = self.library_entry(title="Estatísticas de Saúde", topics=["Saúde"])
        with patch.object(library.store, "connection", side_effect=AssertionError("Filtro não deve reler a coleção")):
            library.query.set("SAUDE")
            self.assertEqual(library.tree.get_children(), (entry["id"],))
            library.query.set("Sem correspondência")
            self.assertEqual(library.tree.get_children(), ())
        library.query.set("")
        library.topic.set("Saúde")
        library.store.save(fields(title="Outro tema", topics=["Economia"]), "Reclassificar referência.", entry["id"], 1)
        library.refresh()
        self.assertEqual(library.topic_options[library.topic.get()], "Saúde")
        self.assertEqual(library.tree.get_children(), ())

    def test_loading_another_session_keeps_catalog_but_clears_the_target(self):
        pane, cid = self.open_dossier()
        library, entry = self.library_entry()
        library.open_for_case()
        other = self.project / "outra-colecao"
        other.mkdir()
        (other / "session.json").write_text('{}', encoding="utf8")
        self.work.load(other)
        self.assertIsNone(library.target)
        self.assertEqual(library.store.entries()[0]["id"], entry["id"])
        self.assertEqual(str(library.use_button["state"]), "disabled")

    def test_unsaved_library_editor_requires_confirmation_to_close(self):
        library = self.work.library
        library.edit()
        window = widgets(self.root, tk.Toplevel)[0]
        widgets(window, ttk.Entry)[0].insert(0, "Cadastro ainda não salvo")
        with patch("factcheck.library_ui.messagebox.askyesno", return_value=False):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.library_ui.messagebox.askyesno", return_value=True):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())
        self.assertEqual(library.store.entries(), [])

    def test_reference_from_imported_document_keeps_unconfirmed_origin_and_original_evidence(self):
        from tests.test_evidence import document
        pane, cid = self.open_dossier()
        doc = {**document(), "acquisition": "local_import", "accessed_at": "", "imported_at": "2026-10-23T10:00:00+00:00", "file_name": "ensaio.html"}
        jid = pane.store.begin(cid, "import")
        pane.store.finish(jid, doc)
        self.work.refresh()
        pane.documents.selection_set(doc["id"])
        pane.save_to_library()
        window = widgets(self.root, tk.Toplevel)[0]
        self.assertTrue(any("origem online precisa" in text.get("1.0", "end") for text in widgets(window, tk.Text)))
        widgets(window, tk.Text)[0].insert("1.0", "Guardar referência para nova pesquisa.")
        next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar referência").invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(pane.store.snapshot(cid)["documents"][0], doc)
        self.assertEqual(len(self.work.library.store.entries()), 1)

    def test_library_storage_failure_does_not_block_the_other_tabs(self):
        with patch("factcheck.library_ui.SourceLibrary", side_effect=PermissionError("Ensaio de pasta indisponível")):
            self.work.library.refresh()
        self.assertIsNone(self.work.library.store)
        self.assertIn("Não foi possível abrir", self.work.library.status.get())
        self.assertFalse(self.work.busy())
        self.assertIsNotNone(self.work.store)

    def topic_entry(self, **changes):
        from tests.test_topics import fields
        pane = self.work.topics
        self.assertTrue(pane.ensure_store())
        entry = pane.store.save(fields(**changes), "Preparar temas fictícios.")
        pane.refresh()
        pane.tree.selection_set(entry["id"])
        pane.show_selected()
        return pane, entry

    def test_topics_manager_registers_without_dossier_or_api_and_shows_history(self):
        pane, entry = self.topic_entry()
        self.assertIsNone(self.work.evidence.cid)
        self.assertEqual(self.work.store.claims(), [])
        self.assertIn("Cadastro", pane.preview.get("1.0", "end"))
        self.assertEqual(pane.tree.get_children(), (entry["id"],))
        self.assertEqual(self.work.ai_config.provider, "local")

    def test_topic_editor_saves_definition_without_starting_triage_or_research(self):
        pane = self.work.topics
        pane.edit()
        window = widgets(self.root, tk.Toplevel)[0]
        name, aliases = widgets(window, ttk.Entry)
        name.insert(0, "Saúde pública")
        aliases.insert(0, "SUS; Saúde coletiva")
        description, reason = widgets(window, tk.Text)
        description.insert("1.0", "Definição fictícia para revisão.")
        reason.insert("1.0", "Preparar vocabulário de ensaio.")
        with patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar tema").invoke()
        triage.assert_not_called()
        research.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(pane.store.entries()[0]["name"], "Saúde pública")
        self.assertEqual(pane.store.entries()[0]["aliases"], ["SUS", "Saúde coletiva"])

    def test_topic_editor_requires_reason_and_confirms_unsaved_close(self):
        pane = self.work.topics
        pane.edit()
        window = widgets(self.root, tk.Toplevel)[0]
        widgets(window, ttk.Entry)[0].insert(0, "Tema ainda não salvo")
        with patch("factcheck.topics_ui.messagebox.showerror") as error:
            next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar tema").invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.topics_ui.messagebox.askyesno", return_value=False):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.topics_ui.messagebox.askyesno", return_value=True):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())
        self.assertEqual(pane.store.entries(), [])

    def test_topic_filters_use_cache_and_archive_restore_preserve_existing_claims(self):
        pane, entry = self.topic_entry(name="Saúde pública", aliases=["SUS"])
        with patch.object(pane.store, "connection", side_effect=AssertionError("Não reler temas para filtrar")):
            pane.query.set("SAUDE SUS")
            self.assertEqual(pane.tree.get_children(), (entry["id"],))
            pane.query.set("Sem correspondência")
            self.assertFalse(pane.tree.selection())
        pane.reset_filters()
        pane.tree.selection_set(entry["id"])
        with patch("factcheck.topics_ui.simpledialog.askstring", return_value="Arquivar no ensaio."):
            pane.archive()
        self.assertEqual(pane.tree.get_children(), ())
        pane.archived.set(True)
        pane.tree.selection_set(entry["id"])
        with patch("factcheck.topics_ui.simpledialog.askstring", return_value="Restaurar no ensaio."):
            pane.archive()
        self.assertFalse(pane.store.entries()[0]["archived"])
        self.assertEqual(len(pane.store.history(entry["id"])), 3)

    def test_claim_topic_suggestions_normalize_registered_alias_and_keep_original_automatic_value(self):
        self.topic_entry()
        pane, cid, window, texts, category, save = self.claim_editor()
        topic = widgets(window, ttk.Combobox)[1]
        self.assertIn("Economia", topic["values"])
        topic.set("INDICE DE PRECOS")
        texts[-1].insert("1.0", "Padronizar tema no ensaio.")
        save.invoke()
        self.assertFalse(window.winfo_exists())
        claim = self.work.claims[cid]
        self.assertEqual(claim["topic"], "Economia")
        self.assertEqual(claim["topic_annotation"]["original"], "INDICE DE PRECOS")
        self.assertEqual(claim["topic_annotation"]["origin"], "operator")
        self.assertEqual(claim["automatic_extraction"]["topic"], "Economia")
        self.assertIsNone(pane.store.snapshot(cid)["decision"])

    def test_claim_topic_editor_preserves_unknown_term_for_review(self):
        self.topic_entry()
        pane, cid, window, texts, category, save = self.claim_editor()
        widgets(window, ttk.Combobox)[1].set("Tema ainda não cadastrado")
        texts[-1].insert("1.0", "Manter tema livre para posterior organização.")
        save.invoke()
        claim = self.work.claims[cid]
        self.assertEqual(claim["topic"], "Tema ainda não cadastrado")
        self.assertEqual(claim["topic_annotation"]["status"], "unmapped")
        self.assertIn("Fora do vocabulário", self.work.claim_detail.get("1.0", "end"))

    def test_claim_topic_editor_rejects_changed_vocabulary_before_saving(self):
        from tests.test_topics import fields
        topics, entry = self.topic_entry()
        pane, cid, window, texts, category, save = self.claim_editor()
        topics.store.save(fields(name="Indicadores econômicos"), "Alterar durante a revisão.", entry["id"], 1)
        texts[-1].insert("1.0", "Editor aberto antes da mudança.")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.store.claims()[0]["claim_revision"], 1)

    def test_topic_storage_failure_does_not_block_capture_or_other_tabs(self):
        with patch("factcheck.topics_ui.TopicStore", side_effect=PermissionError("Pasta fictícia indisponível")):
            self.work.topics.refresh()
        self.assertIsNone(self.work.topics.store)
        self.assertIn("captura pode continuar", self.work.topics.status.get())
        self.assertFalse(self.work.busy())

    def previous_entry(self):
        from tests.test_previous_checks import session
        from factcheck.previous_checks import scan_checked_cases
        review, store, cid = session(self.project / "recordings" / "anterior")
        pane = self.work.previous_checks
        pane.entries = {entry["key"]: entry for entry in scan_checked_cases(self.project / "recordings")["entries"]}
        pane.apply_filters()
        key = next(iter(pane.entries))
        pane.tree.selection_set(key)
        pane.show_selected()
        return pane, review, store, cid, key

    def previous_comparison(self):
        dossier, cid = self.open_dossier()
        pane, review, store, old_cid, key = self.previous_entry()
        pane.open_for_case()
        pane.compare()
        window = widgets(self.root, tk.Toplevel)[0]
        notes = [widget for widget in widgets(window, tk.Text) if str(widget["state"]) == "normal"]
        for widget in notes:
            widget.insert("1.0", "Conferência pendente no ensaio fictício.")
        save = next(button for button in widgets(window, ttk.Button) if button["text"] == "Registrar antecedente consultado")
        return pane, dossier, cid, window, save, store, old_cid

    def test_previous_checks_are_available_without_an_open_dossier_or_api_key(self):
        pane, _, _, _, key = self.previous_entry()
        self.assertIsNone(self.work.evidence.cid)
        self.assertIsNone(pane.target)
        self.assertEqual(str(pane.compare_button["state"]), "disabled")
        self.assertIn("Revisor fictício", pane.preview.get("1.0", "end"))
        self.assertEqual(pane.tree.get_children(), (key,))

    def test_previous_filters_are_local_and_hiding_selection_disables_comparison(self):
        from factcheck.previous_checks import read_checked_cases
        dossier, cid = self.open_dossier()
        pane, _, _, _, key = self.previous_entry()
        pane.open_for_case()
        self.assertEqual(str(pane.compare_button["state"]), "normal")
        with patch("factcheck.previous_checks.sqlite3.connect", side_effect=AssertionError("Não reler o banco")):
            pane.query.set("INFLACAO 2025")
            self.assertEqual(pane.tree.get_children(), (key,))
            pane.query.set("Sem correspondência")
            self.assertFalse(pane.tree.selection())
            self.assertEqual(str(pane.compare_button["state"]), "disabled")
            self.assertNotIn("Revisor fictício", pane.preview.get("1.0", "end"))

    def test_previous_scan_runs_as_activity_and_result_arrives_through_app_events(self):
        pane, _, _, _, key = self.previous_entry()
        from factcheck.previous_checks import scan_checked_cases
        with patch("factcheck.previous_checks_ui.PreviousChecksTask.start") as start:
            pane.refresh()
        start.assert_called_once()
        self.assertIn(pane.task.token, self.app.activities)
        self.assertEqual(str(pane.cancel_button["state"]), "normal")
        pane.task.pending = 0
        pane.task.emit("previous_checks_done", {"token": pane.task.token, "success": True, **scan_checked_cases(Path(pane.folder.get()))})
        self.app.poll()
        self.assertNotIn(pane.task.token, self.app.activities)
        self.assertEqual(len(pane.entries), 1)
        self.assertIn("1 sessões lidas", pane.status.get())

    def test_previous_cancel_requires_confirmation_and_ignores_late_success(self):
        pane, _, _, _, key = self.previous_entry()
        with patch("factcheck.previous_checks_ui.PreviousChecksTask.start"):
            pane.refresh()
        with patch("factcheck.previous_checks_ui.messagebox.askyesno", return_value=False):
            pane.cancel()
        self.assertFalse(pane.task.cancelled.is_set())
        with patch("factcheck.previous_checks_ui.messagebox.askyesno", return_value=True):
            pane.cancel()
        self.assertTrue(pane.task.cancelled.is_set())
        pane.task.pending = 0
        pane.done({"token": pane.task.token, "success": True, "entries": [], "warnings": [], "sessions": 0})
        self.assertIn(key, pane.entries)
        self.assertIn("cancelada", pane.status.get())

    def test_previous_comparison_registers_reference_without_research_or_verdict_transfer(self):
        pane, dossier, cid, window, save, _, _ = self.previous_comparison()
        with patch("factcheck.evidence_ui.ResearchTask") as research, patch("factcheck.workbench.TriageRunner") as triage:
            save.invoke()
        research.assert_not_called()
        triage.assert_not_called()
        self.assertFalse(window.winfo_exists())
        data = dossier.store.snapshot(cid)
        self.assertEqual(len(data["previous_checks"]), 1)
        self.assertEqual(data["documents"], [])
        self.assertIsNone(data["decision"])
        self.assertIsNone(data["preliminary"])
        self.assertEqual(self.app.notebook.select(), str(dossier.tab))

    def test_previous_comparison_rechecks_origin_at_save(self):
        pane, dossier, cid, window, save, store, old_cid = self.previous_comparison()
        store.decide(old_cid, 1, "inconclusiva", "Revisor posterior", "Origem alterada durante a comparação.")
        with patch("factcheck.previous_checks_ui.messagebox.showinfo") as info:
            save.invoke()
        info.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(dossier.store.snapshot(cid)["previous_checks"], [])

    def test_previous_comparison_rechecks_destination_plan_at_save(self):
        pane, dossier, cid, window, save, _, _ = self.previous_comparison()
        dossier.store.save_plan(cid, 0, {"question": "Qual indicador?", "scope": "pesquisavel", "period": "2025", "territory": "Brasil",
            "indicator": "IPCA", "comparison": "", "notes": "", "candidate_urls": []})
        with patch("factcheck.previous_checks_ui.messagebox.showinfo") as info:
            save.invoke()
        info.assert_called_once()
        self.assertEqual(dossier.store.snapshot(cid)["previous_checks"], [])

    def test_previous_comparison_missing_notes_stays_open(self):
        pane, dossier, cid, window, save, _, _ = self.previous_comparison()
        editable = next(widget for widget in widgets(window, tk.Text) if str(widget["state"]) == "normal")
        editable.delete("1.0", "end")
        with patch("factcheck.previous_checks_ui.messagebox.showinfo") as info:
            save.invoke()
        info.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(dossier.store.snapshot(cid)["previous_checks"], [])

    def test_previous_comparison_unsaved_close_requires_confirmation(self):
        pane, dossier, cid, window, save, _, _ = self.previous_comparison()
        with patch("factcheck.previous_checks_ui.messagebox.askyesno", return_value=False):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.previous_checks_ui.messagebox.askyesno", return_value=True):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())
        self.assertEqual(dossier.store.snapshot(cid)["previous_checks"], [])

    def test_previous_target_clears_on_session_change_but_results_remain(self):
        dossier, cid = self.open_dossier()
        pane, _, _, _, key = self.previous_entry()
        pane.open_for_case()
        other = self.project / "outra-sessao-anterior"
        other.mkdir()
        (other / "session.json").write_text('{}', encoding="utf8")
        self.work.load(other)
        self.assertIsNone(pane.target)
        self.assertIn(key, pane.entries)
        self.assertEqual(str(pane.compare_button["state"]), "disabled")

    def test_close_during_previous_scan_confirms_and_waits_for_cancellation(self):
        pane = self.work.previous_checks
        with patch("factcheck.previous_checks_ui.PreviousChecksTask.start"):
            pane.refresh()
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.assertTrue(pane.task.cancelled.is_set())
            destroy.assert_not_called()
            pane.task.pending = 0
            pane.task.emit("previous_checks_done", {"token": pane.task.token, "success": False, "message": "Consulta cancelada."})
            self.app.poll()
            destroy.assert_called_once()

    def assignment_editor(self, existing_name=None):
        pane, cid = self.open_dossier()
        if existing_name is not None:
            self.work.assignment_store.save(cid, 0, 1, 1, existing_name, "Distribuir o acompanhamento do caso.")
            self.work.refresh()
            self.work.claim_tree.selection_set(cid)
        self.work.edit_assignment()
        window = widgets(self.root, tk.Toplevel)[0]
        return window, widgets(window, ttk.Combobox)[0], widgets(window, tk.Text)[-1], cid

    def test_assignment_editor_saves_case_owner_without_changing_the_decision(self):
        window, name, reason, cid = self.assignment_editor()
        name.set("Ana")
        reason.insert("1.0", "Acompanhar as fontes do indicador.")
        next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar atribuição").invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.claim_tree.set(cid, "assignee"), "Ana")
        self.assertEqual(self.work.claims[cid]["assignment"]["revision"], 1)
        self.assertIsNone(self.work.evidence.store.snapshot(cid)["decision"])
        self.assertEqual(self.work.evidence.store.snapshot(cid)["revision"], 0)
        self.assertIn("Responsável pelo caso: Ana", self.work.claim_detail.get("1.0", "end"))

    def test_reassignment_under_filter_clears_selection_and_keeps_the_selected_filter(self):
        window, name, reason, cid = self.assignment_editor("Ana")
        self.work.filter_values["assignee"].set("Ana")
        name.set("Bruna")
        reason.delete("1.0", "end")
        reason.insert("1.0", "Redistribuição da pauta.")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar atribuição").invoke()
        error.assert_not_called()
        self.assertEqual(self.work.claim_tree.get_children(), ())
        self.assertIsNone(self.work.selected_claim())
        self.assertEqual(self.work.filter_options["assignee"][self.work.filter_values["assignee"].get()], "Ana")
        self.work.reset_filters()
        self.assertEqual(self.work.claim_tree.set(cid, "assignee"), "Bruna")

    def test_clear_assignee_returns_case_to_unassigned_and_handles_reserved_names(self):
        window, name, reason, cid = self.assignment_editor("Todos")
        self.work.filter_values["assignee"].set("Todos (cadastrado)")
        self.assertEqual(self.work.claim_tree.get_children(), (cid,))
        next(b for b in widgets(window, ttk.Button) if b["text"] == "Limpar nome").invoke()
        reason.delete("1.0", "end")
        reason.insert("1.0", "Liberado para distribuição.")
        next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar atribuição").invoke()
        self.assertEqual(self.work.claim_tree.get_children(), ())
        self.work.filter_values["assignee"].set("Sem responsável")
        self.assertEqual(self.work.claim_tree.get_children(), (cid,))
        self.assertEqual(self.work.claims[cid]["assignment"]["name"], "")

    def test_assignment_editor_requires_a_reason_and_stays_open_after_validation_error(self):
        window, name, reason, cid = self.assignment_editor()
        name.set("Ana")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar atribuição").invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.assignment_store.all(), {})

    def test_old_assignment_editor_cannot_save_after_extraction_changes(self):
        window, name, reason, cid = self.assignment_editor("Ana")
        claim = self.work.claims[cid]
        fields = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        fields["topic"] = "Indicadores"
        self.work.store.revise_claim(cid, 1, 1, fields, "Tema corrigido.")
        self.work.refresh()
        name.set("Bruna")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar atribuição").invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertTrue(self.work.claims[cid]["assignment"]["needs_review"])
        self.assertEqual(self.work.claims[cid]["assignment"]["name"], "Ana")

    def test_unsaved_assignment_close_requires_confirmation(self):
        window, name, reason, cid = self.assignment_editor()
        name.set("Ana")
        with patch("factcheck.workbench.messagebox.askyesno", return_value=False):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.workbench.messagebox.askyesno", return_value=True):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.assignment_store.all(), {})

    def test_assignee_filter_uses_cache_without_database_reads_or_external_calls(self):
        pane, cid = self.open_dossier()
        self.work.assignment_store.save(cid, 0, 1, 1, "Ana", "Acompanhar as fontes do indicador.")
        self.work.refresh()
        with patch.object(self.work.store, "connection", side_effect=AssertionError("Consulta indevida")), \
                patch.object(self.work.assignment_store, "all", side_effect=AssertionError("Consulta indevida")), \
                patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            self.work.filter_values["assignee"].set("Ana")
            self.assertEqual(self.work.claim_tree.get_children(), (cid,))
            self.work.filter_values["assignee"].set("Sem responsável")
            self.assertEqual(self.work.claim_tree.get_children(), ())
        triage.assert_not_called()
        research.assert_not_called()

    def test_another_session_resets_assignee_filter_and_assignment_data(self):
        pane, cid = self.open_dossier()
        self.work.assignment_store.save(cid, 0, 1, 1, "Ana", "Acompanhar as fontes do indicador.")
        self.work.refresh()
        self.work.filter_values["assignee"].set("Ana")
        other = self.project / "outra-atribuicao"
        other.mkdir()
        (other / "session.json").write_text('{}', encoding="utf8")
        self.work.load(other)
        self.assertEqual(self.work.filter_values["assignee"].get(), "Todos")
        self.assertEqual(self.work.assignment_store.all(), {})
        self.assertNotIn("Ana", self.work.filter_options["assignee"])

    def priority_editor(self, existing=False):
        pane, cid = self.open_dossier()
        if existing:
            self.work.priority_store.save(cid, 0, 1, 1, "high", "Dado relevante e com fonte disponível.")
            self.work.refresh()
            self.work.claim_tree.selection_set(cid)
        self.work.edit_priority()
        window = widgets(self.root, tk.Toplevel)[0]
        return window, widgets(window, ttk.Combobox)[0], widgets(window, tk.Text)[-1], cid

    def test_priority_editor_saves_manual_reason_without_revising_claim_or_case(self):
        window, level, reason, cid = self.priority_editor()
        level.set("Alta")
        reason.insert("1.0", "Indicador central na pauta do ensaio.")
        next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar prioridade").invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.claim_tree.set(cid, "priority"), "Alta")
        self.assertEqual(self.work.claims[cid]["priority"]["reason"], "Indicador central na pauta do ensaio.")
        self.assertEqual(self.work.claims[cid].get("claim_revision", 1), 1)
        self.assertEqual(self.work.evidence.store.snapshot(cid)["revision"], 0)
        self.assertIn("Indicador central", self.work.claim_detail.get("1.0", "end"))

    def test_priority_change_under_filter_saves_and_clears_hidden_selection(self):
        window, level, reason, cid = self.priority_editor(True)
        self.work.filter_values["priority"].set("Alta")
        level.set("Baixa")
        reason.delete("1.0", "end")
        reason.insert("1.0", "A pauta foi reorganizada.")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar prioridade").invoke()
        error.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.claim_tree.get_children(), ())
        self.assertIsNone(self.work.selected_claim())
        self.work.reset_filters()
        self.assertEqual(self.work.claim_tree.set(cid, "priority"), "Baixa")

    def test_old_priority_editor_is_rejected_after_an_extraction_change(self):
        window, level, reason, cid = self.priority_editor(True)
        claim = self.work.claims[cid]
        fields = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        fields["topic"] = "Indicadores"
        self.work.store.revise_claim(cid, 1, 1, fields, "Tema corrigido.")
        self.work.refresh()
        with patch("factcheck.workbench.messagebox.showerror") as error:
            next(b for b in widgets(window, ttk.Button) if b["text"] == "Salvar prioridade").invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertTrue(self.work.claims[cid]["priority"]["needs_review"])
        self.assertEqual(self.work.claims[cid]["priority"]["revision"], 1)

    def test_unsaved_priority_close_requires_confirmation(self):
        window, level, reason, cid = self.priority_editor()
        level.set("Alta")
        with patch("factcheck.workbench.messagebox.askyesno", return_value=False):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertTrue(window.winfo_exists())
        with patch("factcheck.workbench.messagebox.askyesno", return_value=True):
            window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.priority_store.all(), {})

    def test_priority_filter_and_sort_use_cached_data_without_database_or_model_calls(self):
        pane, cid = self.open_dossier()
        self.work.priority_store.save(cid, 0, 1, 1, "high", "Dado central na pauta.")
        self.work.refresh()
        with patch.object(self.work.store, "connection", side_effect=AssertionError("Consulta indevida")), \
                patch.object(self.work.priority_store, "all", side_effect=AssertionError("Consulta indevida")), \
                patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            self.work.filter_values["priority"].set("Alta")
            self.work.claim_order.set("Prioridade")
            self.assertEqual(self.work.claim_tree.get_children(), (cid,))
            self.work.filter_values["priority"].set("Não definida")
            self.assertEqual(self.work.claim_tree.get_children(), ())
        triage.assert_not_called()
        research.assert_not_called()

    def test_opening_another_session_resets_priority_filter_and_order(self):
        pane, cid = self.open_dossier()
        self.work.filter_values["priority"].set("Alta")
        self.work.claim_order.set("Prioridade")
        other = self.project / "outra-fila"
        other.mkdir()
        (other / "session.json").write_text('{}', encoding="utf8")
        self.work.load(other)
        self.assertEqual(self.work.filter_values["priority"].get(), "Todos")
        self.assertEqual(self.work.claim_order.get(), "Mais recentes")
        self.assertEqual(self.work.priority_store.all(), {})

    def open_discovery(self, with_results=True):
        pane, cid = self.open_dossier()
        if with_results:
            from factcheck.discovery import parse_results
            jid = pane.store.begin(cid, "discover", "Inflação 2025 metodologia")
            pane.store.finish(jid, *parse_results({"results": [{"title": "Documento fictício", "url": "https://ibge.gov.br/teste"}]}, "Inflação 2025 metodologia"))
        pane.discover()
        return pane, cid, pane.discovery_dialog

    def test_discovery_requires_own_key_and_can_use_local_triage_without_gemini(self):
        pane, cid, dialog = self.open_discovery(False)
        with patch("factcheck.discovery_ui.messagebox.showinfo") as info, patch("factcheck.evidence_ui.ResearchTask") as task:
            dialog.search()
        info.assert_called_once()
        task.assert_not_called()
        dialog.key.insert(0, "tvly-chave-ficticia")
        self.assertEqual(str(dialog.key["show"]), "*")
        with patch("factcheck.evidence_ui.ResearchTask", FakeDiscoveryTask):
            dialog.search()
        self.assertEqual(pane.task.kind, "discover")
        self.assertEqual(pane.task.config.api_key, "tvly-chave-ficticia")
        self.assertEqual(self.work.ai_config.provider, "local")
        self.assertIn(pane.task.token, self.app.activities)
        for file in self.folder.iterdir():
            if file.is_file():
                self.assertNotIn(b"tvly-chave-ficticia", file.read_bytes())
        dialog.clear_key()
        self.assertEqual(dialog.key.get(), "")
        self.assertEqual(pane.search_config.api_key, "")

    def test_candidate_selection_only_copies_url_and_never_collects_automatically(self):
        pane, cid, dialog = self.open_discovery()
        dialog.tree.selection_set(dialog.tree.get_children()[0])
        with patch("factcheck.evidence_ui.ResearchTask") as task:
            dialog.use()
        task.assert_not_called()
        self.assertEqual(pane.url.get(), "https://ibge.gov.br/teste")
        self.assertEqual(pane.store.snapshot(cid)["documents"], [])
        self.assertFalse(dialog.window.winfo_exists())

    def test_candidate_discard_preserves_reason_and_blocks_use(self):
        pane, cid, dialog = self.open_discovery()
        dialog.tree.selection_set(dialog.tree.get_children()[0])
        with patch("factcheck.discovery_ui.simpledialog.askstring", return_value="Outro período."):
            dialog.discard()
        self.assertEqual(pane.store.snapshot(cid)["discoveries"][0]["candidates"][0]["discard_reason"], "Outro período.")
        with patch("factcheck.discovery_ui.messagebox.showinfo") as info:
            dialog.use()
        info.assert_called_once()
        self.assertEqual(pane.url.get(), "")

    def test_old_candidates_are_hidden_by_default_and_cannot_be_used_as_current(self):
        pane, cid, dialog = self.open_discovery()
        claim = self.work.store.claims()[0]
        fields = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        fields["topic"] = "Indicadores"
        self.work.store.revise_claim(cid, 1, 1, fields, "Tema corrigido.")
        self.work.refresh()
        self.assertEqual(dialog.tree.get_children(), ())
        dialog.historical.set(True)
        dialog.refresh()
        dialog.tree.selection_set(dialog.tree.get_children()[0])
        with patch("factcheck.discovery_ui.messagebox.showinfo") as info:
            dialog.use()
        info.assert_called_once()
        self.assertEqual(pane.url.get(), "")

    def test_discovery_window_close_confirms_cancellation_and_preserves_running_guard(self):
        pane, cid, dialog = self.open_discovery(False)
        dialog.key.insert(0, "tvly-chave-ficticia")
        with patch("factcheck.evidence_ui.ResearchTask", FakeDiscoveryTask):
            dialog.search()
        with patch("factcheck.discovery_ui.messagebox.askyesno", return_value=False):
            dialog.close()
        self.assertTrue(dialog.window.winfo_exists())
        self.assertFalse(pane.task.cancelled.is_set())
        with patch("factcheck.discovery_ui.messagebox.askyesno", return_value=True):
            dialog.close()
        self.assertTrue(pane.task.cancelled.is_set())
        self.assertTrue(pane.busy())
        self.assertFalse(dialog.window.winfo_exists())

    def test_discovery_completion_refreshes_candidates_and_releases_application_guard(self):
        pane, cid, dialog = self.open_discovery()
        pane.task = FakeDiscoveryTask(pane.store, cid, "discover", "Consulta", None, None)
        self.app.register_activity(pane.task.token, "Busca de fontes", pane.task.cancel)
        pane.task.pending = 0
        self.app.events.put(("research_done", {"token": pane.task.token, "claim_id": cid, "message": "Busca concluída."}))
        self.app.poll()
        self.assertNotIn(pane.task.token, self.app.activities)
        self.assertEqual(len(dialog.tree.get_children()), 1)
        self.assertEqual(dialog.status.get(), "Busca concluída.")
        self.assertEqual(str(dialog.cancel_button["state"]), "disabled")

    def test_queue_filters_hide_selection_without_database_reads_or_ai_calls(self):
        pane, cid = self.open_dossier()
        before = self.work.store.path.read_bytes()
        with patch.object(self.work.store, "connection", side_effect=AssertionError("Filtro não deve consultar SQLite")), \
                patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            self.work.claim_query.set("TERMO INEXISTENTE")
            self.assertEqual(self.work.claim_tree.get_children(), ())
            self.assertIsNone(self.work.selected_claim())
            self.work.claim_query.set("inflacao 2025")
            self.assertEqual(self.work.claim_tree.get_children(), (cid,))
        triage.assert_not_called()
        research.assert_not_called()
        self.assertEqual(self.work.store.path.read_bytes(), before)
        self.assertIn("Exibindo 1 de 1", self.work.claim_count.get())

    def test_queue_scope_state_and_export_scope_remain_consistent_after_discard(self):
        pane, cid = self.open_dossier()
        self.work.store.discard_claim(cid, "Teste de descarte.")
        self.work.refresh()
        self.work.claim_scope.set("Somente atuais")
        self.assertEqual(self.work.claim_tree.get_children(), ())
        self.work.claim_scope.set("Históricas / descartadas")
        self.work.filter_values["state"].set("Descartada")
        self.assertEqual(self.work.claim_tree.get_children(), (cid,))
        self.work.claim_query.set("Sem correspondência")
        self.assertEqual(self.work.claim_tree.get_children(), ())
        from factcheck.exports import snapshot
        self.assertEqual(len(snapshot(self.work.store, True)["claims"]), 1)
        self.work.reset_filters()
        self.assertEqual(self.work.claim_tree.get_children(), (cid,))

    def test_reclassifying_under_category_filter_saves_even_when_row_disappears(self):
        pane, cid = self.open_dossier()
        self.work.filter_values["category"].set("Factual")
        self.work.edit_claim()
        window = widgets(self.root, tk.Toplevel)[0]
        widgets(window, ttk.Combobox)[0].set("Opinião")
        widgets(window, tk.Text)[-1].insert("1.0", "Reclassificação fictícia para testar o filtro.")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar revisão da extração").invoke()
        error.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.claim_tree.get_children(), ())
        self.assertIsNone(self.work.selected_claim())
        self.assertEqual(self.work.claims[cid]["category"], "opiniao")
        self.work.reset_filters()
        self.assertEqual(self.work.claim_tree.get_children(), (cid,))

    def test_filter_values_follow_claim_metadata_and_new_session_resets_filters(self):
        pane, cid = self.open_dossier()
        self.work.filter_values["topic"].set("Economia")
        claim = self.work.claims[cid]
        fields = {key: claim.get(key) for key in ("quote", "summary", "category", "topic")}
        fields["topic"] = "Saúde"
        self.work.store.revise_claim(cid, 1, 1, fields, "Tema do exemplo fictício.")
        self.work.refresh()
        self.assertIn("Saúde", self.work.filter_options["topic"])
        self.assertEqual(self.work.filter_options["topic"][self.work.filter_values["topic"].get()], "Economia")
        self.assertEqual(self.work.claim_tree.get_children(), ())
        self.work.filter_values["topic"].set("Saúde")
        self.work.filter_values["speaker"].set("Não identificado")
        self.assertEqual(self.work.claim_tree.get_children(), (cid,))
        self.work.claim_query.set("nada")
        other = self.project / "outra-sessao"
        other.mkdir()
        (other / "session.json").write_text('{}', encoding="utf8")
        self.work.load(other)
        self.assertEqual(self.work.claim_query.get(), "")
        self.assertEqual(self.work.claim_scope.get(), "Todas")
        self.assertTrue(all(variable.get() == "Todos" for variable in self.work.filter_values.values()))
        self.assertEqual(self.work.claim_tree.get_children(), ())

    def claim_editor(self):
        pane, cid = self.open_dossier()
        self.work.edit_claim()
        window = widgets(self.root, tk.Toplevel)[0]
        texts = widgets(window, tk.Text)
        category = widgets(window, ttk.Combobox)[0]
        save = next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar revisão da extração")
        return pane, cid, window, texts, category, save

    def test_claim_editor_reclassifies_without_running_ai_or_approving_the_source_or_fact(self):
        pane, cid, window, texts, category, save = self.claim_editor()
        category.set("Opinião")
        texts[-1].insert("1.0", "Classificação corrigida no ensaio fictício.")
        with patch("factcheck.workbench.TriageRunner") as triage, patch("factcheck.evidence_ui.ResearchTask") as research:
            save.invoke()
        triage.assert_not_called()
        research.assert_not_called()
        current = self.work.claims[cid]
        self.assertEqual(current["category"], "opiniao")
        self.assertEqual(current["claim_revision"], 2)
        self.assertEqual(current["automatic_extraction"]["category"], "fato")
        self.assertFalse(self.work.store.source(1)["human_reviewed"])
        self.assertIsNone(pane.store.snapshot(cid)["decision"])
        self.assertIn("revisada pelo operador", self.work.claim_detail.get("1.0", "end"))
        self.assertFalse(window.winfo_exists())

    def test_claim_editor_invalid_quote_stays_open_and_preserves_data(self):
        pane, cid, window, texts, category, save = self.claim_editor()
        quote = texts[1]
        quote.delete("1.0", "end")
        quote.insert("1.0", "Trecho que não existe.")
        texts[-1].insert("1.0", "Revisão fictícia.")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.store.claims()[0]["quote"], self.text)

    def test_claim_editor_rejects_concurrent_revision_and_preserves_newer_version(self):
        pane, cid, window, texts, category, save = self.claim_editor()
        source = self.work.store.claims()[0]
        fields = {key: source.get(key) for key in ("quote", "summary", "category", "topic")}
        fields["category"] = "promessa"
        self.work.store.revise_claim(cid, 1, 1, fields, "Revisão mais recente.")
        category.set("Opinião")
        texts[-1].insert("1.0", "Editor antigo.")
        with patch("factcheck.workbench.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.store.claims()[0]["category"], "promessa")

    def test_claim_editor_cancel_requires_confirmation_for_unsaved_changes(self):
        pane, cid, window, texts, category, save = self.claim_editor()
        category.set("Indefinida")
        cancel = next(button for button in widgets(window, ttk.Button) if button["text"] == "Cancelar")
        with patch("factcheck.workbench.messagebox.askyesno", return_value=False):
            cancel.invoke()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(self.work.store.claims()[0]["category"], "fato")
        with patch("factcheck.workbench.messagebox.askyesno", return_value=True):
            cancel.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.store.claims()[0]["category"], "fato")

    def test_plan_editor_saves_recuts_without_running_ai_or_approving_facts(self):
        pane, cid = self.open_dossier()
        pane.plan()
        window = widgets(self.root, tk.Toplevel)[0]
        question, notes, urls = widgets(window, tk.Text)
        question.insert("1.0", "Qual indicador está sendo comparado?")
        notes.insert("1.0", "Definir o período antes de pesquisar.")
        urls.insert("1.0", "https://ibge.gov.br/")
        with patch("factcheck.evidence_ui.ResearchTask") as research, patch("factcheck.workbench.TriageRunner") as triage:
            next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar planejamento").invoke()
        research.assert_not_called()
        triage.assert_not_called()
        result = pane.store.snapshot(cid)
        self.assertEqual(result["plan"]["question"], "Qual indicador está sendo comparado?")
        self.assertEqual(result["plan"]["period"], "")
        self.assertEqual(result["plan"]["origin"], "operator_input")
        self.assertIsNone(result["decision"])
        self.assertEqual(result["documents"], [])
        self.assertFalse(self.work.store.source(1)["human_reviewed"])

    def test_cancel_dirty_plan_requires_confirmation_and_keeps_database_unchanged(self):
        pane, cid = self.open_dossier()
        pane.plan()
        window = widgets(self.root, tk.Toplevel)[0]
        widgets(window, tk.Text)[0].insert("1.0", "Pergunta ainda não salva")
        cancel = next(button for button in widgets(window, ttk.Button) if button["text"] == "Cancelar")
        with patch("factcheck.evidence_ui.messagebox.askyesno", return_value=False):
            cancel.invoke()
        self.assertTrue(window.winfo_exists())
        self.assertIsNone(pane.store.snapshot(cid)["plan"])
        with patch("factcheck.evidence_ui.messagebox.askyesno", return_value=True):
            cancel.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertIsNone(pane.store.snapshot(cid)["plan"])

    def test_stale_plan_editor_preserves_newer_decision_and_stays_open(self):
        pane, cid = self.open_dossier()
        pane.plan()
        window = widgets(self.root, tk.Toplevel)[0]
        question, notes, _ = widgets(window, tk.Text)
        question.insert("1.0", "Pergunta antiga?")
        notes.insert("1.0", "Contexto a definir.")
        pane.store.decide(cid, 0, "inconclusiva", "Revisor fictício", "Decisão posterior à abertura.")
        with patch("factcheck.evidence_ui.messagebox.showerror") as error:
            next(button for button in widgets(window, ttk.Button) if button["text"] == "Salvar planejamento").invoke()
        error.assert_called_once()
        self.assertTrue(window.winfo_exists())
        self.assertIsNotNone(pane.store.snapshot(cid)["decision"])

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
