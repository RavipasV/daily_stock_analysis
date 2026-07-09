# -*- coding: utf-8 -*-
"""Shared market-symbol helpers for suffix-only offshore markets.

Keep this module dependency-light so it can be used by data providers, market
context, trading calendars, stock-index loading, and API input normalization
without introducing import cycles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SuffixMarketSpec:
    """A suffix-only Yahoo Finance market rule."""

    market: str
    suffixes: tuple[str, ...]
    digit_lengths: tuple[int, ...]
    # Markets with alphabetic tickers (e.g. Thailand PTT.BK) validate the base
    # against _ALPHA_BASE_PATTERN instead of digit_lengths.
    alpha_base: bool = False


# Alphabetic-ticker base: starts with a letter, then letters/digits (e.g. PTT,
# ADVANC, S11). Deliberately conservative so numeric CN/HK-style codes and
# dotted US forms like BRK.B can never match an alpha-base market by accident.
_ALPHA_BASE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")

_SUFFIX_MARKET_SPECS: tuple[SuffixMarketSpec, ...] = (
    SuffixMarketSpec("jp", ("T",), (4, 5)),
    SuffixMarketSpec("kr", ("KS", "KQ"), (6,)),
    # Taiwan support mirrors the same suffix-only pattern; keep it here so the
    # shared helpers stay complete for all yfinance-only offshore markets.
    SuffixMarketSpec("tw", ("TW", "TWO"), (4, 5, 6)),
    # Thailand (SET): alphabetic tickers such as PTT.BK / ADVANC.BK; only the
    # explicit `.BK` suffix opts a code into the Thai market.
    SuffixMarketSpec("th", ("BK",), (), alpha_base=True),
)

_MARKET_TO_SPEC = {spec.market: spec for spec in _SUFFIX_MARKET_SPECS}
_SUFFIX_TO_SPEC = {
    suffix: spec
    for spec in _SUFFIX_MARKET_SPECS
    for suffix in spec.suffixes
}


def split_suffix_symbol(stock_code: str) -> tuple[str, str] | None:
    """Return ``(base, suffix)`` for dotted symbols, upper-cased and stripped."""

    code = (stock_code or "").strip().upper()
    if "." not in code:
        return None
    base, suffix = code.rsplit(".", 1)
    if not base or not suffix:
        return None
    return base, suffix


def get_suffix_market(stock_code: str) -> Optional[str]:
    """Return jp/kr/tw/th for supported suffix-only Yahoo symbols, else None."""

    parts = split_suffix_symbol(stock_code)
    if parts is None:
        return None
    base, suffix = parts
    spec = _SUFFIX_TO_SPEC.get(suffix)
    if spec is None:
        return None
    if spec.alpha_base:
        if not _ALPHA_BASE_PATTERN.match(base):
            return None
        return spec.market
    if not (base.isdigit() and len(base) in spec.digit_lengths):
        return None
    return spec.market


def is_suffix_market_symbol(stock_code: str, market: Optional[str] = None) -> bool:
    """Return whether a stock code is a supported suffix-only Yahoo symbol."""

    detected = get_suffix_market(stock_code)
    if market is None:
        return detected is not None
    return detected == (market or "").strip().lower()


def is_jp_suffix_symbol(stock_code: str) -> bool:
    return is_suffix_market_symbol(stock_code, "jp")


def is_kr_suffix_symbol(stock_code: str) -> bool:
    return is_suffix_market_symbol(stock_code, "kr")


def is_tw_suffix_symbol(stock_code: str) -> bool:
    return is_suffix_market_symbol(stock_code, "tw")


def is_th_suffix_symbol(stock_code: str) -> bool:
    return is_suffix_market_symbol(stock_code, "th")


def normalize_suffix_market_symbol(stock_code: str) -> Optional[str]:
    """Normalize supported suffix-only symbols to upper-case Yahoo form."""

    parts = split_suffix_symbol(stock_code)
    if parts is None:
        return None
    base, suffix = parts
    if get_suffix_market(f"{base}.{suffix}") is None:
        return None
    return f"{base}.{suffix}"


def suffix_base_lookup_allowed(canonical_code: str) -> bool:
    """Return True when a suffix-market code may be resolved from its bare base.

    JP/KR intentionally allow stock-index-backed bare-code lookup to support the
    existing MVP behavior. TW remains strict suffix-only for now because its
    follow-up index work is not part of this issue.
    """

    return get_suffix_market(canonical_code) in {"jp", "kr"}


def market_suffixes(market: str) -> tuple[str, ...]:
    spec = _MARKET_TO_SPEC.get((market or "").strip().lower())
    return spec.suffixes if spec else ()
