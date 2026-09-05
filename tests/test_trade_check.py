#!/usr/bin/env python3
"""Behavioral verifier for the trade-check skill.

Runs the skill's own offline scenario suite, which exercises the five entry
rules end to end against synthetic Alpha Vantage / Tiingo payloads and asserts
the expected verdict for each, then checks that the backtest helpers emit a
parseable engine for every strategy. It is stdlib-only, needs no network and no
API quota, and writes only inside a temporary directory.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELFTEST = ROOT / "skills" / "trade-check" / "scripts" / "selftest.py"


class TradeCheckScenarioTests(unittest.TestCase):
    def test_offline_scenarios_produce_expected_verdicts(self) -> None:
        self.assertTrue(SELFTEST.is_file(), f"missing verifier: {SELFTEST}")
        result = subprocess.run(
            [sys.executable, str(SELFTEST)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0,
            result.returncode,
            f"trade-check selftest failed\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}",
        )
        self.assertIn("all scenarios behaved as expected", result.stdout)
        # A silent pass would be indistinguishable from a suite that ran nothing.
        self.assertNotIn("FAIL", result.stdout)
        self.assertGreaterEqual(
            result.stdout.count("ok  "),
            8,
            f"expected the full scenario set to run, got:\n{result.stdout}",
        )


if __name__ == "__main__":
    unittest.main()
