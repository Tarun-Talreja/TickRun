#!/usr/bin/env python3
"""Validate daily.json / weekly_screens.json against runtime JSON schemas.

Usage:
    python tests/validate_output.py daily
    python tests/validate_output.py weekly
"""
import json
import os
import sys

from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DAILY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["last_updated", "market_context", "tickers", "flags"],
    "properties": {
        "last_updated": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"},
        "market_context": {
            "type": "object",
            "required": ["spy_price", "qqq_price", "vix", "ten_year_yield"],
            "properties": {
                "spy_price": {"type": ["number", "null"]},
                "spy_change_pct": {"type": ["number", "null"]},
                "qqq_price": {"type": ["number", "null"]},
                "qqq_change_pct": {"type": ["number", "null"]},
                "vix": {"type": ["number", "null"]},
                "ten_year_yield": {"type": ["number", "null"]},
            },
        },
        "tickers": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["symbol", "price"],
                "properties": {
                    "symbol": {"type": "string", "minLength": 1},
                    "price": {"type": ["number", "null"]},
                    "change_pct_1d": {"type": ["number", "null"]},
                    "change_pct_5d": {"type": ["number", "null"]},
                    "change_pct_ytd": {"type": ["number", "null"]},
                    "range_52w_low": {"type": ["number", "null"]},
                    "range_52w_high": {"type": ["number", "null"]},
                    "pe": {"type": ["number", "null"]},
                    "forward_pe": {"type": ["number", "null"]},
                    "rsi_14": {"type": ["number", "null"]},
                    "ma_50": {"type": ["number", "null"]},
                    "ma_200": {"type": ["number", "null"]},
                    "next_earnings": {"type": ["string", "null"]},
                    "news_titles_24h": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["symbol", "type", "detail"],
                "properties": {
                    "symbol": {"type": "string"},
                    "type": {"enum": ["earnings_soon", "big_move", "rsi_extreme", "ma_cross"]},
                    "detail": {"type": "string"},
                },
            },
        },
    },
}


WEEKLY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["last_updated", "universe", "screens_run", "top_conviction", "by_screen"],
    "properties": {
        "last_updated": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"},
        "universe": {"type": "string"},
        "screens_run": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "total_passes": {"type": ["integer", "null"]},
        "top_conviction": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["symbol", "company", "sector", "price", "screens_passed", "score"],
                "properties": {
                    "symbol": {"type": "string"},
                    "company": {"type": "string"},
                    "sector": {"type": "string"},
                    "price": {"type": ["number", "null"]},
                    "screens_passed": {"type": "array", "items": {"type": "string"}},
                    "score": {"type": "integer", "minimum": 1},
                    "one_line_thesis": {"type": "string"},
                },
            },
        },
        "by_screen": {"type": "object"},
        "sector_mix_top20": {"type": "object"},
    },
}


def validate(kind: str) -> int:
    if kind == "daily":
        path = os.path.join(ROOT, "output", "daily.json")
        schema = DAILY_SCHEMA
    elif kind == "weekly":
        path = os.path.join(ROOT, "output", "weekly_screens.json")
        schema = WEEKLY_SCHEMA
    else:
        print(f"Unknown kind: {kind}")
        return 2

    with open(path) as f:
        data = json.load(f)

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        print(f"❌ {kind}.json failed schema validation:")
        for err in errors[:20]:
            location = "/".join(str(p) for p in err.path) or "<root>"
            print(f"  - {location}: {err.message}")
        return 1
    print(f"✅ {kind}.json passes schema validation")
    return 0


if __name__ == "__main__":
    sys.exit(validate(sys.argv[1] if len(sys.argv) > 1 else "daily"))
