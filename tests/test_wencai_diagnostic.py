"""Diagnostic unit tests for Wencai query compatibility; no network required."""
import unittest
from unittest.mock import patch
import pandas as pd

def fetch(query, client):
    result = client.get(query=query, query_type="stock", loop=True)
    if not isinstance(result, pd.DataFrame) or result.empty:
        raise RuntimeError("Wencai returned no usable table")
    return result

class WencaiTests(unittest.TestCase):
    def test_simple_query(self):
        client = unittest.mock.Mock()
        client.get.return_value = pd.DataFrame({"股票代码": ["000001"]})
        self.assertEqual(len(fetch("历史新高", client)), 1)

    def test_dated_query(self):
        client = unittest.mock.Mock()
        client.get.return_value = pd.DataFrame({"股票代码": ["000001"]})
        fetch("2026-10-30 A股 上市以来历史新高", client)
        self.assertEqual(client.get.call_args.kwargs["query_type"], "stock")

    def test_empty_response_fails_closed(self):
        client = unittest.mock.Mock()
        for response in (None, pd.DataFrame()):
            client.get.return_value = response
            with self.assertRaises(RuntimeError):
                fetch("历史新高", client)

if __name__ == "__main__":
    unittest.main()
