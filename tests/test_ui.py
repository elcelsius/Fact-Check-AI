from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from factcheck.audio import AudioDevice
from factcheck.paragraphs import ParagraphAssembler
from factcheck.transcription import TranscriptLine
from factcheck.ui import CaptureApp


@unittest.skipUnless(sys.platform == "win32", "Interface Windows")
class CancellationUITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        with patch("factcheck.ui.loopback_devices", return_value=[AudioDevice(1, "Test", 100, 1)]):
            self.app = CaptureApp(self.root, Path(self.directory.name))
        self.session = Mock()
        self.session.cancel_event = threading.Event()
        self.session.cancel.side_effect = self.session.cancel_event.set
        self.app.session = self.session
        self.app.cancel_button.configure(state="normal")
        self.app.stop_button.configure(state="normal")

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.directory.cleanup()

    def test_declining_confirmation_keeps_session_running(self):
        with patch("factcheck.ui.messagebox.askyesno", return_value=False) as confirm:
            self.app.cancel_button.invoke()
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        self.session.cancel.assert_not_called()
        self.session.stop.assert_not_called()
        self.assertEqual(str(self.app.cancel_button["state"]), "normal")

    def test_confirming_cancels_and_prevents_double_click(self):
        with patch("factcheck.ui.messagebox.askyesno", return_value=True) as confirm:
            self.app.cancel_button.invoke()
            self.app.cancel()
        confirm.assert_called_once()
        self.session.cancel.assert_called_once()
        self.assertEqual(str(self.app.cancel_button["state"]), "disabled")
        self.assertEqual(str(self.app.stop_button["state"]), "disabled")

    def test_cancelled_completion_restores_start_and_reports_preserved_files(self):
        self.app.events.put(("done", {"success": False, "cancelled": True,
                                      "folder": "existing-session"}))
        self.app.poll()
        self.assertIsNone(self.app.session)
        self.assertEqual(str(self.app.start_button["state"]), "normal")
        self.assertEqual(str(self.app.cancel_button["state"]), "disabled")
        self.assertIn("cancelada", self.app.status["text"])

    def test_partial_revisions_replace_text_without_appending_to_history(self):
        self.app.events.put(("partial", {"text": "dez"}))
        self.app.events.put(("partial", {"text": "doze"}))
        self.app.poll()
        self.assertEqual(self.app.partial.get("1.0", "end-1c"), "doze")
        self.assertEqual(self.app.transcript.get("1.0", "end-1c"), "")

    def test_cancel_clears_partial_and_ignores_queued_recognition_results(self):
        self.app.set_partial("em andamento")
        self.app.events.put(("partial", {"text": "resultado tardio"}))
        self.app.events.put(("transcript", {"text": "tardio", "start": 0, "end": 1}))
        paragraph = ParagraphAssembler().add(TranscriptLine(0, 1, "a fala tardia chegou"), 1)[0]
        self.app.events.put(("paragraph", paragraph))
        with patch("factcheck.ui.messagebox.askyesno", return_value=True):
            self.app.cancel()
        self.app.poll()
        self.assertEqual(self.app.partial.get("1.0", "end-1c"), "")
        self.assertEqual(self.app.transcript.get("1.0", "end-1c"), "")

    def test_declining_window_close_preserves_recording_and_controls(self):
        self.app.set_partial("a fala continua")
        with patch("factcheck.ui.messagebox.askyesno", return_value=False) as confirm, \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        self.assertIn("perdidos", confirm.call_args.args[1])
        self.assertIn("preservados", confirm.call_args.args[1])
        self.assertFalse(self.app.closing)
        self.session.cancel.assert_not_called()
        self.session.stop.assert_not_called()
        destroy.assert_not_called()
        self.assertEqual(self.app.partial.get("1.0", "end-1c"), "a fala continua")
        self.assertEqual(str(self.app.cancel_button["state"]), "normal")

    def test_confirmed_close_cancels_once_and_waits_until_files_are_finalized(self):
        with patch("factcheck.ui.messagebox.askyesno", return_value=True) as confirm, \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.app.close()
            self.session.cancel.assert_called_once()
            self.session.stop.assert_not_called()
            destroy.assert_not_called()
            self.app.events.put(("done", {"success": False, "cancelled": True, "folder": "saved"}))
            self.app.poll()
            destroy.assert_called_once()
        confirm.assert_called_once()

    def test_checking_activity_without_recording_also_requires_confirmation_and_completion(self):
        self.app.session = None
        cancel_check = Mock()
        self.app.register_activity("check-1", "Checagem de fatos", cancel_check)
        with patch("factcheck.ui.messagebox.askyesno", return_value=True) as confirm, \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
            cancel_check.assert_called_once()
            destroy.assert_not_called()
            self.app.events.put(("activity_done", {"id": "check-1"}))
            self.app.poll()
            destroy.assert_called_once()
        confirm.assert_called_once()

    def test_close_waits_for_both_recording_and_checking_activity(self):
        cancel_check = Mock()
        self.app.register_activity("check-1", "Checagem de fatos", cancel_check)
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.app.events.put(("done", {"success": False, "cancelled": True, "folder": "saved"}))
            self.app.poll()
            destroy.assert_not_called()
            self.app.events.put(("activity_done", {"id": "check-1"}))
            self.app.poll()
            destroy.assert_called_once()

    def test_idle_close_does_not_prompt(self):
        self.app.session = None
        with patch("factcheck.ui.messagebox.askyesno") as confirm, \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
        confirm.assert_not_called()
        destroy.assert_called_once()

    def test_repeated_close_while_confirmation_is_open_does_not_open_second_dialog(self):
        def answer(*args, **kwargs):
            self.app.close()
            return False

        with patch("factcheck.ui.messagebox.askyesno", side_effect=answer) as confirm:
            self.app.close()
        confirm.assert_called_once()
        self.assertFalse(self.app.closing)

    def test_failed_background_cancellation_keeps_window_open_and_other_tasks_receive_cancel(self):
        self.app.session = None
        self.app.register_activity("check-1", "Checagem", Mock(side_effect=RuntimeError("Falha simulada")))
        other = Mock()
        self.app.register_activity("check-2", "Outra checagem", other)
        with patch("factcheck.ui.messagebox.askyesno", return_value=True), \
                patch("factcheck.ui.messagebox.showerror") as error, \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
        error.assert_called_once()
        destroy.assert_not_called()
        other.assert_called_once()
        self.assertFalse(self.app.closing)

    def test_session_completing_while_close_dialog_is_open_is_safe(self):
        def answer(*args, **kwargs):
            self.app.events.put(("done", {"success": True, "cancelled": False, "folder": "saved"}))
            self.app.poll()
            return True

        with patch("factcheck.ui.messagebox.askyesno", side_effect=answer), \
                patch.object(self.root, "destroy") as destroy:
            self.app.close()
            destroy.assert_called_once()

    def test_paragraph_revision_replaces_tail_and_original_toggle_preserves_words(self):
        assembler = ParagraphAssembler()
        for data in assembler.add(TranscriptLine(0, 2, "criamos vinte mil empregos"), 1):
            self.app.update_paragraph(data)
        update = assembler.add(TranscriptLine(4, 6, "no estado"), 2)[-1]
        self.app.update_paragraph(update)
        self.app.update_paragraph(update)  # A mesma versão não é inserida novamente.
        text = self.app.transcript.get("1.0", "end-1c")
        self.assertEqual(text.count("Criamos"), 1)
        self.assertIn("Criamos vinte mil empregos no estado.", text)
        self.app.show_original.set(True)
        self.app.render_paragraphs()
        self.assertIn("criamos vinte mil empregos no estado", self.app.transcript.get("1.0", "end-1c"))

    def test_closed_paragraph_is_not_duplicated_when_new_paragraph_arrives(self):
        assembler = ParagraphAssembler()
        for data in assembler.add(TranscriptLine(0, 2, "a renda cresceu"), 1):
            self.app.update_paragraph(data)
        for data in assembler.add(TranscriptLine(5, 7, "o índice caiu"), 2):
            self.app.update_paragraph(data)
        text = self.app.transcript.get("1.0", "end-1c")
        self.assertEqual(text.count("A renda cresceu"), 1)
        self.assertEqual(text.count("O índice caiu"), 1)


if __name__ == "__main__":
    unittest.main()
