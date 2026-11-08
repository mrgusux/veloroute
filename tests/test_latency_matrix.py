"""Unit tests for Enhanced LatencyTracker and SLA Health Matrix."""
import unittest
from veloroute.core.router import LatencyTracker


class TestLatencyMatrix(unittest.TestCase):
    def setUp(self):
        self.tracker = LatencyTracker()

    def test_record_and_percentiles(self):
        # Record 10 sample latencies for 'mock'
        samples = [100.0, 110.0, 105.0, 120.0, 95.0, 115.0, 130.0, 102.0, 108.0, 250.0]
        for s in samples:
            self.tracker.record("mock", s, success=True)

        matrix = self.tracker.get_matrix("mock")
        self.assertIsNotNone(matrix)
        self.assertEqual(matrix["provider"], "mock")
        self.assertEqual(matrix["sample_count"], 10)
        self.assertGreater(matrix["p95_latency_ms"], matrix["p50_latency_ms"])
        self.assertEqual(matrix["min_latency_ms"], 95.0)
        self.assertEqual(matrix["max_latency_ms"], 250.0)
        self.assertEqual(matrix["availability_pct"], 100.0)
        self.assertEqual(matrix["status"], "healthy")

    def test_error_recording_and_availability(self):
        # 8 successes, 2 failures
        for _ in range(8):
            self.tracker.record("failing_prov", 150.0, success=True)
        for _ in range(2):
            self.tracker.record("failing_prov", 0.0, success=False)

        matrix = self.tracker.get_matrix("failing_prov")
        self.assertEqual(matrix["sample_count"], 10)
        self.assertEqual(matrix["availability_pct"], 80.0)
        self.assertEqual(matrix["status"], "degraded")

    def test_all_matrix(self):
        self.tracker.record("prov1", 50.0)
        self.tracker.record("prov2", 120.0)

        all_m = self.tracker.get_all_matrix()
        self.assertEqual(len(all_m), 2)
        prov_names = [m["provider"] for m in all_m]
        self.assertIn("prov1", prov_names)
        self.assertIn("prov2", prov_names)


if __name__ == "__main__":
    unittest.main()
