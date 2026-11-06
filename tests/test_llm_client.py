"""A cut-off response must not pass for a finished one."""
import os
import sys
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import llm_client


def _chunk(text, reason=None):
    choice = SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=reason)
    return SimpleNamespace(choices=[choice])


def _fake_client(responses):
    """responses: model -> (text, finish_reason), or an exception to raise mid-stream."""
    def create(model, stream=False, **_):
        assert stream, "chat must stream, or a slow model dies at the timeout"
        def chunks():
            outcome = responses[model]
            if isinstance(outcome, Exception):
                yield _chunk("partial")
                raise outcome
            text, reason = outcome
            yield SimpleNamespace(choices=[])          # keep-alive chunks have no choices
            yield _chunk(text[:2])
            yield _chunk(text[2:], reason)
        return chunks()
    completions = SimpleNamespace(create=create)
    return lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_streamed_text_is_joined(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _fake_client({"a": ("hello there", "stop")}))
    assert llm_client.chat("k", [], max_tokens=5, models=["a"]) == ("hello there", "a")


def test_stall_mid_stream_falls_through(monkeypatch):
    responses = {"a": httpx.ReadTimeout("stalled"), "b": ("done", "stop")}
    monkeypatch.setattr("openai.OpenAI", _fake_client(responses))
    assert llm_client.chat("k", [], max_tokens=5, models=["a", "b"]) == ("done", "b")


def test_model_over_the_time_limit_falls_through(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _fake_client({"a": ("slow", "stop")}))
    monkeypatch.setattr(llm_client, "MAX_STREAM_SECONDS", -1)
    with pytest.raises(RuntimeError):
        llm_client.chat("k", [], max_tokens=5, models=["a"])


def test_stops_trying_models_after_the_deadline(monkeypatch):
    tried = []
    def create(model, **_):
        tried.append(model)
        return iter([_chunk("x", "stop")])
    completions = SimpleNamespace(create=create)
    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    monkeypatch.setattr(llm_client, "CHAT_DEADLINE_SECONDS", -1)
    with pytest.raises(RuntimeError):
        llm_client.chat("k", [], max_tokens=5, models=["a", "b"])
    assert tried == []


def test_truncated_response_falls_through(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _fake_client({"a": ("half a no", "length"), "b": ("done", "stop")}))
    assert llm_client.chat("k", [], max_tokens=5, models=["a", "b"]) == ("done", "b")


def test_only_truncated_responses_raise(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", _fake_client({"a": ("half a no", "length")}))
    with pytest.raises(RuntimeError):
        llm_client.chat("k", [], max_tokens=5, models=["a"])
