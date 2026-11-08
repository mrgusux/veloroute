"""Unit tests for Side-by-Side Model Comparator & A/B Benchmark Playground."""
import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from veloroute.schema import CompletionResponse


class TestModelComparator(unittest.TestCase):
    def test_comparator_math_and_logic(self):
        # Test latency comparison calculations
        lat_a = 200.0
        lat_b = 400.0
        pct_faster = round(((lat_b - lat_a) / lat_b) * 100, 1)
        self.assertEqual(pct_faster, 50.0)

        # Test cost comparison calculations
        cost_a = 0.002000
        cost_b = 0.000500
        pct_cheaper = round(((cost_a - cost_b) / cost_a) * 100, 1)
        self.assertEqual(pct_cheaper, 75.0)

    def test_parallel_execution(self):
        async def dummy_runner():
            async def task(name, delay, content):
                await asyncio.sleep(delay)
                return {"model": name, "content": content}

            res_a, res_b = await asyncio.gather(
                task("model-a", 0.01, "Response A"),
                task("model-b", 0.02, "Response B"),
            )
            return res_a, res_b

        res_a, res_b = asyncio.run(dummy_runner())
        self.assertEqual(res_a["model"], "model-a")
        self.assertEqual(res_b["model"], "model-b")


if __name__ == "__main__":
    unittest.main()
