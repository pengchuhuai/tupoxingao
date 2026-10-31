import json
import tempfile
import unittest
from pathlib import Path
from sector_monitor import build

class TestSectorMonitor(unittest.TestCase):
    def test_candidates_never_count_as_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / "candidates").mkdir()
            (p / "candidates" / "2026-10-30.json").write_text(json.dumps({"date": "2026-10-30", "candidates": [{"code": "000001", "industry": "银行"}]}))
            (p / "breakouts.json").write_text(json.dumps([
                {"ts_code": "000002.SZ", "date": "20261030", "basis": "raw", "verification": "source_history_fetched"},
                {"ts_code": "000002.SZ", "date": "20261030", "basis": "hfq", "verification": "source_history_fetched"}]))
            (p / "industry_map.json").write_text(json.dumps({"000002.SZ": "电子"}))
            report = build(p, "20261030")
            self.assertEqual(report["verified_total_unique_stock_industry_pairs"], 1)
            self.assertEqual(report["verified_highs_by_industry"][0]["industry"], "电子")
            self.assertEqual(report["reported_closing_high_candidates_by_industry"][0]["industry"], "银行")

if __name__ == "__main__":
    unittest.main()
