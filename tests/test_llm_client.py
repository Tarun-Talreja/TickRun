"""A cut-off response must not pass for a finished one."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import llm_client


def _fake_client(responses):
    """responses: model -> (text, finish_reason)."""
    def create(model, **_):
        text, reason = responses[model]
        choice = SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=reason)
        return SimpleNamespace(choices=[choice])
    completions = SimpleNamespace(create=create)
    return lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_truncated_response_falls_through(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _fake_client({"a": ("half a no", "length"), "b": ("done", "stop")}))
    assert llm_client.chat("k", [], max_tokens=5, models=["a", "b"]) == ("done", "b")


def test_only_truncated_responses_raise(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _fake_client({"a": ("half a no", "length")}))
    with pytest.raises(RuntimeError):
        llm_client.chat("k", [], max_tokens=5, models=["a"])
