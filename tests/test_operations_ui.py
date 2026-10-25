import sys
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from factcheck.evidence_notes_ui import open_notes
from factcheck.manual_claims_ui import open_editor
from factcheck.research_queue_ui import open_queue
from factcheck.usage import DEFAULTS
from tests.test_evidence import document
from tests import test_workbench as ui_fixtures

widgets = ui_fixtures.widgets


@unittest.skipUnless(sys.platform == "win32", "Interface Windows")
class LocalOperationsUITests(unittest.TestCase):
    setUp = ui_fixtures.WorkbenchTests.setUp
    tearDown = ui_fixtures.WorkbenchTests.tearDown

    def window(self): return widgets(self.root, tk.Toplevel)[0]

    def button(self, window, label):
        return next(item for item in widgets(window, ttk.Button) if item["text"] == label)

    def claim(self):
        claim = self.work.store.create_claims(1, 1, [{"quote": self.text, "summary": self.text, "category": "fato", "topic": None}], "Teste fictício.")[0]
        self.work.refresh()
        self.work.claim_tree.selection_set(claim["id"])
        self.work.evidence.open_selected()
        return claim

    def test_manual_editor_saves_literal_claim_and_never_starts_an_ai_task(self):
        open_editor(self.work)
        window = self.window()
        editors = [item for item in widgets(window, tk.Text) if str(item["state"]) == "normal"]
        for item, value in zip(editors, (self.text, self.text, "Inclusão fictícia pelo operador.")): item.insert("1.0", value)
        with patch("factcheck.workbench.TriageRunner") as triage:
            self.button(window, "Incluir afirmação").invoke()
        triage.assert_not_called()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(self.work.store.claims()[0]["creation"]["origin"], "operator_input")

    def test_unsaved_manual_editor_declined_cancel_keeps_text_and_activity(self):
        open_editor(self.work)
        window = self.window()
        next(item for item in widgets(window, tk.Text) if str(item["state"]) == "normal").insert("1.0", self.text)
        with patch("factcheck.manual_claims_ui.messagebox.askyesno", return_value=False):
            self.button(window, "Cancelar").invoke()
        self.assertTrue(window.winfo_exists())
        self.assertTrue(any(token.startswith("editor-") for token in self.app.activities))
        self.assertEqual(self.work.store.claims(), [])

    def test_citation_editor_saves_selected_literal_evidence_without_a_factual_decision(self):
        claim = self.claim()
        store = self.work.evidence.store
        store.finish(store.begin(claim["id"], "collect"), document(), {})
        open_notes(self.work.evidence)
        window = self.window()
        editors = widgets(window, tk.Text)
        editors[-1].insert("1.0", "Trecho de fonte fictícia, a conferir.")
        self.button(window, "Salvar anotação").invoke()
        self.assertFalse(window.winfo_exists())
        snapshot = store.snapshot(claim["id"])
        self.assertEqual(snapshot["work_notes"][0]["kind"], "citation")
        self.assertIsNone(snapshot["decision"])

    def test_operation_limits_dialog_saves_zero_and_preserves_unknown_prices(self):
        pane = self.work.operations
        pane.configure()
        window = self.window()
        maximum = next(item for item in widgets(window, ttk.Entry) if not isinstance(item, ttk.Combobox))
        maximum.delete(0, "end"); maximum.insert(0, "0")
        self.button(window, "Salvar limites").invoke()
        self.assertEqual(pane.usage.settings()["max_api_calls"], 0)
        self.assertIsNone(pane.usage.settings()["gemini_per_million_tokens"])

    def test_reference_requires_explicit_no_facts_confirmation(self):
        source = self.work.store.source(1)
        self.work.store.revise(1, source["revision"], source["text"], None, reviewed=True)
        self.work.refresh()
        pane = self.work.operations
        pane.reference()
        window = self.window()
        widgets(window, ttk.Entry)[1].insert(0, "Anotador fictício")
        with patch("factcheck.operations_ui.messagebox.showerror") as error:
            self.button(window, "Salvar referência").invoke()
        error.assert_called_once()
        self.assertEqual(pane.evaluation.references(), {})
        widgets(window, ttk.Checkbutton)[0].invoke()
        self.button(window, "Salvar referência").invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(pane.evaluation.references()[1]["expected_facts"], [])

    def test_file_operation_registers_close_guard_and_cancel_confirmation(self):
        task = SimpleNamespace(token="files-fixture", pending=1, start=Mock(), cancel=Mock())
        with patch("factcheck.operations_ui.FileTask", return_value=task):
            self.work.operations.begin("backup", Mock(), ())
        self.assertIn(task.token, self.app.activities)
        with patch("factcheck.operations_ui.messagebox.askyesno", return_value=False): self.work.operations.cancel()
        task.cancel.assert_not_called()
        with patch("factcheck.operations_ui.messagebox.askyesno", return_value=True): self.work.operations.cancel()
        task.cancel.assert_called_once()
        task.pending = 0
        self.work.operations.done({"token": task.token, "error": None, "result": {"path": "ficticio.fcbak"}})
        self.assertNotIn(task.token, self.app.activities)

    def test_paused_and_stopping_status_are_not_overwritten_by_backlog_events(self):
        self.app.session = SimpleNamespace(stop_event=threading.Event(), pause_event=threading.Event())
        data = {"dbfs": -10, "peak": .2, "queued_chunks": 30}
        self.app.session.pause_event.set()
        self.app.status.configure(text="Pausado")
        self.app.events.put(("level", data)); self.app.poll()
        self.assertEqual(self.app.status["text"], "Pausado")
        self.app.session.pause_event.clear(); self.app.session.stop_event.set()
        self.app.status.configure(text="Finalizando")
        self.app.events.put(("level", data)); self.app.poll()
        self.assertEqual(self.app.status["text"], "Finalizando")

    def test_backlog_message_clears_after_queue_recovers(self):
        self.app.session = SimpleNamespace(stop_event=threading.Event(), pause_event=threading.Event())
        self.app._capture_message = "Capturando áudio."
        for queue in (30, 0):
            self.app.events.put(("level", {"dbfs": -10, "peak": .2, "queued_chunks": queue}))
            self.app.poll()
        self.assertEqual(self.app.status["text"], "Capturando áudio.")

    def test_pause_click_racing_with_capture_completion_does_not_raise_or_change_status(self):
        self.app.session = SimpleNamespace(stop_event=threading.Event(), pause_event=threading.Event(),
            set_paused=Mock(side_effect=ValueError("Captura finalizada.")))
        self.app.status.configure(text="Finalizando")
        self.app.toggle_pause()
        self.assertEqual(str(self.app.pause_button["state"]), "disabled")
        self.assertEqual(self.app.status["text"], "Finalizando")

    def test_queue_start_rechecks_research_started_after_dialog_was_opened(self):
        self.claim()
        open_queue(self.work)
        window = self.window()
        self.work.evidence.task = SimpleNamespace(pending=1)
        with patch("factcheck.research_queue_ui.ResearchQueue") as queue, patch("factcheck.research_queue_ui.messagebox.showerror") as error:
            self.button(window, "Começar pesquisas").invoke()
        queue.assert_not_called()
        error.assert_called_once()

    def test_failed_queue_start_and_audit_write_do_not_leave_app_waiting_to_close(self):
        self.claim()
        open_queue(self.work)
        window = self.window()
        batch = SimpleNamespace(token="batch-fixture", bid="fixture", pending=1, data={}, cancel=Mock(),
            start=Mock(side_effect=RuntimeError("Falha de thread simulada.")),
            audit=SimpleNamespace(save=Mock(side_effect=sqlite3.OperationalError("Disco simulado indisponível."))))
        with patch("factcheck.research_queue_ui.ResearchQueue", return_value=batch), patch("factcheck.research_queue_ui.messagebox.showerror") as error:
            self.button(window, "Começar pesquisas").invoke()
        self.assertNotIn(batch.token, self.app.activities)
        self.assertEqual(batch.pending, 0)
        error.assert_called_once()


if __name__ == "__main__": unittest.main()
