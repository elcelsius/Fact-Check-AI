import json
import unittest

from factcheck.usage import ApiLimit, DEFAULTS, UsageStore
from factcheck.research import ResearchTask
from factcheck.discovery import SearchConfig
from unittest.mock import patch
from tests import test_evidence as fixtures


class UsageTests(unittest.TestCase):
    setUp = fixtures.DossierTests.setUp
    tearDown = fixtures.DossierTests.tearDown

    def test_limit_is_reserved_atomically_before_send_and_zero_blocks_new_calls(self):
        usage = UsageStore(self.review)
        usage.configure(0, {**DEFAULTS, "max_api_calls": 1})
        usage.reserve("first", "gemini", "triage")
        with self.assertRaises(ApiLimit): usage.reserve("second", "tavily", "discover")
        usage.complete("first", "cancelled")
        self.assertEqual(usage.summary()["remaining_calls"], 0)
        self.assertEqual(usage.summary()["unpriced_or_unreported_attempts"], 1)

    def test_cost_is_unknown_without_usage_or_reference_prices_and_explicit_zero_is_allowed(self):
        usage = UsageStore(self.review)
        usage.reserve("first", "gemini", "triage")
        usage.complete("first", "completed", {"usage": {"totalTokenCount": 1000}})
        self.assertIsNone(usage.summary()["estimated_cost"])
        usage.configure(0, {**DEFAULTS, "gemini_per_million_tokens": "0", "budget": "0"})
        self.assertEqual(usage.summary()["estimated_cost"], "0")

    def test_estimate_uses_operator_rates_and_does_not_store_free_form_engine_or_credentials(self):
        usage = UsageStore(self.review)
        usage.configure(0, {**DEFAULTS, "gemini_per_million_tokens": "2", "tavily_per_credit": "0.1", "budget": "1"})
        usage.reserve("first", "gemini", "triage")
        usage.complete("first", "completed", {"usage": {"totalTokenCount": 1000000, "api_key": "SECRET"}, "api_key": "SECRET"})
        usage.reserve("second", "tavily", "discover")
        usage.complete("second", "completed", {"credits": 2})
        result = usage.summary()
        self.assertEqual(result["estimated_cost"], "2.2")
        self.assertTrue(result["budget_warning"])
        self.assertEqual(result["estimated_remaining_budget"], "0")
        with self.review.connection() as db:
            self.assertNotIn("SECRET", str(db.execute("SELECT payload FROM api_requests").fetchall()))

    def test_zero_limit_blocks_discovery_before_network_worker_is_started(self):
        usage = UsageStore(self.review)
        usage.configure(0, {**DEFAULTS, "max_api_calls": 0})
        task = ResearchTask(self.store, self.cid, "discover", "taxa Brasil 2025", SearchConfig("FICTITIOUS-KEY"), lambda *_: None)
        with patch("factcheck.research._network_worker") as network:
            task._run()
        network.assert_not_called()
        self.assertEqual(self.store.snapshot(self.cid)["jobs"][0]["status"], "failed")
        self.assertEqual(usage.summary()["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
