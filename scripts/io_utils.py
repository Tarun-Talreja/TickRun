"""Shared file helpers."""

import json
import os


def load_json(path: str, default=None):
    """Parsed JSON at path, or default ({} if unset) when missing or unreadable."""
    fallback = {} if default is None else default
    if not os.path.exists(path):
        return fallback
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        print(f"⚠ could not read {path}: {exc}")
        return fallback
