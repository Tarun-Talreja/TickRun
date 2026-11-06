"""quotes_cache.json is gitignored, so a job that forgets to refresh quotes has
none. Building anyway published a dashboard with 4 of 57 stocks priced."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import build_dashboard


def test_refuses_to_build_without_quotes(tmp_path, monkeypatch):
    output = tmp_path / "dashboard.json"
    monkeypatch.setattr(build_dashboard, "QUOTES_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(build_dashboard, "OUTPUT_PATH", str(output))
    with pytest.raises(SystemExit) as exc:
        build_dashboard.main()
    assert exc.value.code == 1
    assert not output.exists()
