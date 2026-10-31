import unittest
from backtest import summarize
class BacktestTests(unittest.TestCase):
    def test_empty_never_fabricates_returns(self):
        s=summarize([],[])
        self.assertEqual(s["trades"]["n"],0)
        self.assertIsNone(s["trades"]["mean"])
        self.assertEqual(s["by_regime"]["up"]["trades"]["n"],0)
if __name__=="__main__":
    unittest.main()
