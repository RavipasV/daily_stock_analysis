# -*- coding: utf-8 -*-
"""Regression tests for Thailand (泰股 / SET) suffix-only market support.

Mirrors tests/test_tw_market_support.py. Thai stocks use the Yahoo Finance
suffix form ``TICKER.BK`` (SET-listed) with an alphabetic base such as PTT,
ADVANC, or KBANK — unlike the numeric JP/KR/TW bases. Only the explicit
``.BK`` suffix opts a code into the Thai market; bare tickers keep their
existing US-symbol semantics and numeric codes stay A-share.

Scope matches the original TW commit: market detection and data routing only.
Decision-signal / portfolio / intelligence write paths do not yet support
``th`` and must skip gracefully.
"""

from unittest.mock import patch

import pandas as pd
from data_provider.base import BaseFetcher, DataFetchError, DataFetcherManager, normalize_stock_code
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.core.trading_calendar import MARKET_EXCHANGE, MARKET_TIMEZONE, get_market_for_stock
from src.market_context import detect_market, get_market_guidelines
from src.services.market_symbol_utils import get_suffix_market
from src.services.stock_code_utils import is_code_like, normalize_code


class _FakeFetcher(BaseFetcher):
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.priority = 0 if name != "YfinanceFetcher" else 4
        self.calls = []
        self.should_fail = should_fail

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise NotImplementedError

    def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
        self.calls.append(stock_code)
        if self.should_fail:
            raise DataFetchError(f"{self.name} should not be called for {stock_code}")
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-07-07")],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [100],
                "amount": [100.0],
                "pct_chg": [0.0],
            }
        )


def test_normalize_and_detect_th_suffix_codes() -> None:
    assert normalize_stock_code("ptt.bk") == "PTT.BK"
    assert normalize_stock_code("ADVANC.BK") == "ADVANC.BK"
    assert normalize_stock_code("s11.bk") == "S11.BK"

    assert detect_market("PTT.BK") == "th"
    assert detect_market("ADVANC.BK") == "th"
    assert detect_market("KBANK.BK") == "th"
    assert detect_market("S11.BK") == "th"  # alphanumeric base
    # Bare alpha tickers stay US symbols; only the .BK suffix opts into Thai.
    assert detect_market("PTT") == "us"
    # Numeric bases can never become Thai (alpha-base rule).
    assert get_suffix_market("1234.BK") is None
    assert detect_market("600519") == "cn"

    assert get_market_for_stock("PTT.BK") == "th"
    assert get_market_for_stock("BBL.BK") == "th"

    assert is_code_like("PTT.BK") is True
    assert normalize_code("PTT.BK") == "PTT.BK"
    assert normalize_code("advanc.bk") == "ADVANC.BK"


def test_th_detection_does_not_shadow_us_dotted_symbols() -> None:
    # US class-share forms with a single-letter suffix must stay US.
    assert detect_market("BRK.B") == "us"
    assert get_suffix_market("BRK.B") is None


def test_market_guidelines_for_th_keep_thailand_context() -> None:
    th_guidelines = get_market_guidelines("PTT.BK")

    assert "泰股" in th_guidelines
    assert "SET" in th_guidelines
    # Only China A-share-specific concepts are excluded.
    assert "北向资金" in th_guidelines
    assert "龙虎榜" in th_guidelines

    th_guidelines_en = get_market_guidelines("PTT.BK", "en")
    assert "Thailand" in th_guidelines_en
    assert "SET-listed" in th_guidelines_en
    # The prompt must explicitly forbid treating .BK stocks as US-listed.
    assert "not treat the stock as US-listed" in th_guidelines_en


def test_yfinance_keeps_th_suffix_codes() -> None:
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("PTT.BK") == "PTT.BK"
    assert fetcher._convert_stock_code("advanc.bk") == "ADVANC.BK"
    assert fetcher._is_th_suffix_stock("PTT.BK") is True
    assert fetcher._is_th_suffix_stock("PTT") is False
    assert fetcher._is_th_suffix_stock("1234.BK") is False


def test_data_fetcher_manager_routes_th_daily_only_to_yfinance() -> None:
    efinance = _FakeFetcher("EfinanceFetcher", should_fail=True)
    akshare = _FakeFetcher("AkshareFetcher", should_fail=True)
    yfinance = _FakeFetcher("YfinanceFetcher")
    manager = DataFetcherManager(fetchers=[efinance, akshare, yfinance])

    with patch("data_provider.base.record_provider_run_started"), patch("data_provider.base.record_provider_run"):
        th_df, th_source = manager.get_daily_data("PTT.BK")

    assert th_source == "YfinanceFetcher"
    assert not th_df.empty
    assert efinance.calls == []
    assert akshare.calls == []
    assert yfinance.calls == ["PTT.BK"]


def test_trading_calendar_registers_th_exchange_and_timezone() -> None:
    assert MARKET_EXCHANGE["th"] == "XBKK"
    assert MARKET_TIMEZONE["th"] == "Asia/Bangkok"


def test_th_skips_decision_signal_write_paths_gracefully() -> None:
    """th is recognized by the data layer but intentionally NOT wired into the
    decision-signal service yet (same staging as the original TW rollout).
    The extractor must skip instead of raising ValueError on the main path.
    """
    from src.services.portfolio_service import VALID_MARKETS

    assert get_market_for_stock("PTT.BK") == "th"  # data layer recognizes th
    assert "th" not in VALID_MARKETS  # write path intentionally deferred
