import json
import threading
import unittest
from unittest.mock import patch

from factcheck.exports import ExportTask, read_session, write_export
from factcheck.reporting import elapsed, render_report, session_report, statistics
from tests import test_exports as export_fixtures


class ReportTests(unittest.TestCase):
    setUp = export_fixtures.ExportTests.setUp
    tearDown = export_fixtures.ExportTests.tearDown
    analyze = export_fixtures.ExportTests.analyze
    add_document = export_fixtures.ExportTests.add_document

    def write_events(self, events):
        (self.folder / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf8")

    def test_missing_telemetry_and_reference_are_unavailable_instead_of_zero_or_perfect_accuracy(self):
        report = session_report(self.review)
        self.assertIsNone(report["timing_seconds"]["first_partial"])
        self.assertIsNone(report["timing_seconds"]["chunk_processing"]["median"])
        self.assertIsNone(report["quality"]["precision"])
        self.assertIsNone(report["quality"]["recall"])
        self.assertIsNone(report["quality"]["transcript_word_error_rate"])
        self.assertEqual(report["claims"]["human_decisions_on_detected_factual"], {"numerator": 0, "denominator": 1, "fraction": 0})
        self.assertNotIn("MARCADOR-SECRETO", json.dumps(report))
        self.assertNotIn("A inflação", render_report(report))

    def test_old_report_without_planning_fields_remains_readable(self):
        report = session_report(self.review)
        del report["claims"]["planning"]
        text = render_report(report)
        self.assertIn("não registrado neste relatório antigo", text)
        self.assertIn("NÃO AVALIADOS", text)

    def test_human_decisions_ratio_uses_current_factual_claims_and_excludes_opinions(self):
        self.dossiers.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Sem fonte neste ensaio.")
        report = session_report(self.review)
        self.assertEqual(report["claims"]["current"], 2)
        self.assertEqual(report["claims"]["detected_factual"], 1)
        self.assertEqual(report["claims"]["human_decisions_on_detected_factual"]["fraction"], 1)
        self.assertEqual(report["claims"]["factual_flow"]["human_decided"], 1)
        self.assertIn("NÃO AVALIADOS", render_report(report))
        self.assertIsNone(report["quality"]["precision"])

    def test_editing_origin_removes_stale_decision_and_claim_from_current_denominator(self):
        self.dossiers.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Ensaio.")
        self.review.revise(1, 1, "Fala corrigida.", None)
        report = session_report(self.review)
        self.assertEqual(report["claims"]["detected_factual"], 0)
        self.assertEqual(report["claims"]["historical_or_discarded"], 1)
        self.assertIsNone(report["claims"]["human_decisions_on_detected_factual"]["fraction"])
        self.assertEqual(report["timing_seconds"]["claim_to_current_human_decision"]["observations"], 0)

    def test_manual_grouping_counts_active_composite_once_and_ignores_hidden_components(self):
        self.review.combine(1, 1, 2, 1, True)
        report = session_report(self.review)
        self.assertEqual(report["paragraphs"]["active"], 1)
        self.assertEqual(report["claims"]["current"], 0)
        self.assertEqual(report["claims"]["historical_or_discarded"], 2)

    def test_factual_pending_stages_change_after_import_and_human_review(self):
        report = session_report(self.review)
        self.assertEqual(report["claims"]["factual_flow"]["pending_sources"], 1)
        self.add_document()
        report = session_report(self.review)
        self.assertEqual(report["claims"]["factual_flow"]["sources_only"], 1)
        self.assertEqual(sum(report["claims"]["factual_flow"].values()), 1)
        self.dossiers.decide(self.cid, 1, "inconclusiva", "Revisor fictício", "Origem a conferir.")
        report = session_report(self.review)
        self.assertEqual(report["claims"]["factual_flow"]["sources_only"], 0)
        self.assertEqual(report["claims"]["factual_flow"]["human_decided"], 1)

    def test_incomplete_log_retains_valid_measurements_and_reports_missing_lines(self):
        events = [{"kind": "first_partial", "elapsed_seconds": 1.5},
                  {"kind": "transcript_delivered", "elapsed_seconds": 3.1, "delivery_lag_seconds": .6},
                  {"kind": "transcription_chunk", "processing_seconds": .1, "delivery_lag_seconds": .2, "queued_chunks": 3}]
        self.write_events(events)
        with (self.folder / "events.jsonl").open("ab") as stream:
            stream.write(b'{"kind":"corta\xc3')
        report = session_report(self.review)
        self.assertEqual(report["log"]["invalid_lines"], 1)
        self.assertEqual(report["log"]["first_invalid_line"], 4)
        self.assertEqual(report["timing_seconds"]["first_partial"], 1.5)
        self.assertEqual(report["timing_seconds"]["first_stabilized_delivery"], 3.1)
        self.assertEqual(report["timing_seconds"]["stabilized_delivery_lag"]["median"], .6)
        self.assertEqual(report["history"]["maximum_logged_asr_queue"], 3)
        self.assertTrue(any("Log parcial" in notice for notice in report["notices"]))

    def test_invalid_measurements_are_counted_and_not_converted_to_zero(self):
        self.write_events([{"kind": "transcription_chunk", "processing_seconds": -3, "delivery_lag_seconds": float("nan")},
                           {"kind": "transcription_chunk", "processing_seconds": 0, "delivery_lag_seconds": "2"}])
        report = session_report(self.review)
        timing = report["timing_seconds"]
        self.assertEqual(timing["chunk_processing"]["observations"], 1)
        self.assertEqual(timing["chunk_processing"]["excluded"], 1)
        self.assertEqual(timing["chunk_processing"]["minimum"], 0)
        self.assertIsNone(timing["chunk_delivery_lag"]["median"])
        json.dumps(report, allow_nan=False)

    def test_current_decision_waiting_time_uses_claim_registration_and_explicit_capture_start(self):
        metadata = json.loads((self.folder / "session.json").read_text(encoding="utf8"))
        (self.folder / "session.json").write_text(json.dumps({**metadata, "capture_started_at": "2026-10-23T12:00:00+00:00"}), encoding="utf8")
        self.write_events([{"kind": "started", "at": "2026-10-23T12:00:10+00:00"}])
        with self.review.connection() as db:
            claim = json.loads(db.execute("SELECT payload FROM claims WHERE id=?", (self.cid,)).fetchone()[0])
            claim["created_at"] = "2026-10-23T12:00:20+00:00"
            db.execute("UPDATE claims SET payload=? WHERE id=?", (json.dumps(claim), self.cid))
        with patch("factcheck.dossiers.now", return_value="2026-10-23T12:00:50+00:00"):
            self.dossiers.decide(self.cid, 0, "inconclusiva", "Revisor fictício", "Ensaio.")
        report = session_report(self.review)
        self.assertEqual(report["timing_seconds"]["claim_to_current_human_decision"]["median"], 30)
        self.assertEqual(report["timing_seconds"]["first_current_human_decision_since_capture"], 50)
        self.assertEqual(report["capture"]["time_anchor"]["source"], "capture_started_at")

    def test_clock_rollback_and_naive_timestamps_are_not_valid_waiting_time(self):
        self.assertIsNone(elapsed("2026-10-23T12:00:00+00:00", "2026-10-23T12:00:10+00:00"))
        self.assertIsNone(elapsed("2026-10-23T12:00:10", "2026-10-23T12:00:00"))
        self.assertEqual(elapsed("2026-10-23T09:00:10-03:00", "2026-10-23T12:00:00+00:00"), 10)

    def test_old_start_event_is_explicitly_marked_approximate_without_inventing_first_preview(self):
        self.write_events([{"kind": "started", "at": "2026-10-23T12:00:10+00:00"}])
        report = session_report(self.review)
        self.assertEqual(report["capture"]["time_anchor"]["source"], "started_event_approximation")
        self.assertIsNone(report["timing_seconds"]["first_partial"])

    def test_report_does_not_rewrite_database_or_original_capture_files(self):
        self.write_events([{"kind": "warning", "code": "transcription_error", "message": "MARCADOR-SECRETO"}])
        before = {path: path.read_bytes() for path in self.folder.iterdir() if path.is_file()}
        report = session_report(self.review)
        self.assertEqual(report["history"]["capture_warning_codes"], {"transcription_error": 1})
        self.assertNotIn("MARCADOR-SECRETO", render_report(report))
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_invalid_legacy_metadata_and_unknown_warning_shape_remain_explicit(self):
        (self.folder / "session.json").write_bytes(b'{"incompleto":')
        self.write_events([{"kind": "warning", "code": {"private": "MARCADOR-SECRETO"}}])
        report = session_report(self.review)
        self.assertEqual(report["capture"]["state"], "unknown")
        self.assertEqual(report["history"]["capture_warning_codes"], {"other": 1})
        self.assertTrue(any("Metadados" in notice for notice in report["notices"]))
        self.assertNotIn("MARCADOR-SECRETO", json.dumps(report))

    def test_aggregate_counts_use_one_database_snapshot_during_concurrent_revision(self):
        saved = read_session(self.review)
        self.review.revise(1, 1, "Correção posterior ao retrato.", None)
        with patch("factcheck.reporting.read_session", return_value=saved):
            report = session_report(self.review)
        self.assertEqual(report["claims"]["detected_factual"], 1)
        self.assertEqual(session_report(self.review)["claims"]["detected_factual"], 0)

    def test_p95_requires_twenty_observations_and_uses_linear_interpolation(self):
        values = statistics(list(range(1, 21)) + [-1, None, "2", True, float("nan")])
        self.assertEqual(values["observations"], 20)
        self.assertEqual(values["excluded"], 5)
        self.assertEqual(values["median"], 10.5)
        self.assertAlmostEqual(values["p95"], 19.05)
        self.assertIsNone(statistics(list(range(19)))["p95"])

    def test_unchanged_report_has_stable_content_hash_and_separate_generation_time(self):
        first = session_report(self.review)
        second = session_report(self.review)
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        self.assertNotEqual(first["generated_at"], second["generated_at"])

    def test_json_and_text_exports_are_real_files_and_cancel_keeps_previous_output(self):
        report = session_report(self.review)
        for kind, suffix in (("report_json", ".json"), ("report_txt", ".txt")):
            target = self.root / (kind + suffix)
            write_export(report, target, kind, self.folder)
            if suffix == ".json":
                self.assertEqual(json.loads(target.read_text(encoding="utf8")), report)
            else:
                self.assertIn("RELATÓRIO DO ENSAIO", target.read_text(encoding="utf8"))
            original = target.read_bytes()
            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(InterruptedError):
                write_export(report, target, kind, self.folder, cancelled)
            self.assertEqual(target.read_bytes(), original)

    def test_report_generation_is_blocked_during_active_capture(self):
        with patch("factcheck.reporting.capture_state", return_value=("active", "")), self.assertRaises(ValueError):
            session_report(self.review)

    def test_report_export_task_uses_real_report_and_completes_existing_close_guard(self):
        done, events = threading.Event(), []
        target = self.root / "relatorio.txt"
        task = ExportTask(self.review, target, "report_txt", False, lambda kind, data: (events.append((kind, data)), done.set()))
        task.start()
        self.assertTrue(done.wait(5))
        self.assertFalse(task.pending)
        self.assertTrue(events[0][1]["success"])
        self.assertIn("RELATÓRIO DO ENSAIO", target.read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
