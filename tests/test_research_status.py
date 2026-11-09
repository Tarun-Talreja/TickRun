"""A run with nothing due must still record that it ran, or health calls it dead."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import research_batch


def test_write_status_records_an_empty_run(tmp_path, monkeypatch):
    path = tmp_path / "research_status.json"
    monkeypatch.setattr(research_batch, "STATUS_PATH", str(path))
    research_batch.write_status(attempted=0, landed=[], failures=[])
    saved = json.loads(path.read_text())
    assert saved["attempted"] == 0 and saved["landed"] == 0 and saved["ran_at"]
