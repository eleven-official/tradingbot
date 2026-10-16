import unittest
from unittest.mock import patch

from loki.api.binance_market_data import (
    MarketDataError,
    _snapshot_cache,
    get_binance_spot_snapshot,
)


def candle(close, volume):
    return [0, "1", str(close + 1), "1", str(close), str(volume), 0, "0", 0, "0", "0", "0"]


class BinanceSpotMarketDataTests(unittest.TestCase):
    def setUp(self):
        _snapshot_cache.clear()

    def test_snapshot_maps_public_ticker_book_and_candles(self):
        candles = [candle(100 + index * 0.2, 10 + (index % 3)) for index in range(30)]

        def fake_fetch(path, params):
            if path.endswith("ticker/24hr"):
                return {"lastPrice": "106", "closeTime": "9999999999999", "priceChangePercent": "2.5"}
            if path.endswith("bookTicker"):
                return {"bidPrice": "105.9", "askPrice": "106.1"}
            return candles

        with patch("loki.api.binance_market_data._fetch_json", side_effect=fake_fetch):
            snapshot = get_binance_spot_snapshot("btcusdt", "1m")

        self.assertEqual(snapshot.provider, "Binance Spot public market data")
        self.assertEqual(snapshot.symbol, "BTCUSDT")
        self.assertEqual(snapshot.current_price, 106)
        self.assertEqual(snapshot.trend, "BULLISH")
        self.assertGreater(snapshot.volume_ratio, 0)
        self.assertGreater(snapshot.spread_percent, 0)
        self.assertEqual(snapshot.candle_count, 30)

    def test_invalid_symbols_are_rejected_before_any_request(self):
        with self.assertRaisesRegex(MarketDataError, "symbol"):
            get_binance_spot_snapshot("BTC/USDT")

    def test_invalid_interval_is_rejected_before_any_request(self):
        with self.assertRaisesRegex(MarketDataError, "interval"):
            get_binance_spot_snapshot("BTCUSDT", "10m")

    def test_snapshot_is_briefly_cached(self):
        candles = [candle(100 + index * 0.2, 10) for index in range(30)]
        payloads = [
            {"lastPrice": "106", "closeTime": "9999999999999", "priceChangePercent": "2.5"},
            {"bidPrice": "105.9", "askPrice": "106.1"},
            candles,
        ]
        with patch("loki.api.binance_market_data._fetch_json", side_effect=payloads) as fetch:
            get_binance_spot_snapshot("BTCUSDT")
            get_binance_spot_snapshot("BTCUSDT")

        self.assertEqual(fetch.call_count, 3)


if __name__ == "__main__":
    unittest.main()

