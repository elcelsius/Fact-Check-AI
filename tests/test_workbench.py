from dataclasses import asdict
import json
from pathlib import Path
import sys
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
from factcheck.ui import CaptureApp


def widgets(parent, kind):
    found = []
    for child in parent.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(widgets(child, kind))
    return found


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
        provider.current(1)
        apply.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.ai_config.provider, "gemini")
        self.assertIn("texto enviado ao Google", self.work.ai_label.get())
        self.assertIsNone(self.work.runner)
        for file in self.project.rglob("*"):
            if file.is_file():
                self.assertNotIn(b"chave-de-teste", file.read_bytes())

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
