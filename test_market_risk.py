import unittest
from market_risk import assess_market,size_position
class MarketRiskTests(unittest.TestCase):
    def test_missing_inputs_fail_closed(self):
        a=assess_market(trend=90)
        self.assertEqual(a.regime,"unknown")
        self.assertEqual(size_position(100000,100000,10,9,0,0,a),0)
    def test_thresholds(self):
        self.assertEqual(assess_market(90,90,90,90).max_exposure,1)
        self.assertEqual(assess_market(20,20,20,20).max_exposure,.1)
    def test_risk_and_lot(self):
        a=assess_market(90,90,90,90)
        self.assertEqual(size_position(100000,100000,10,9,0,0,a),1000)
        self.assertEqual(size_position(100000,100000,10,9,1,0,a),0)
        self.assertEqual(size_position(100000,100000,10,9,0,.4,a),0)
if __name__=="__main__":
    unittest.main()
