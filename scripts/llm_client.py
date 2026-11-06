#!/usr/bin/env python3
"""
scripts/llm_client.py — The ONE place that knows which NVIDIA NIM chat models to use.

WHY THIS EXISTS
On 2026-08-26 NVIDIA retired meta/llama-3.3-70b-instruct (HTTP 410 Gone). Four
scripts each hardcoded it, and research_ticker.py's fallback loop only caught
NotFoundError/timeouts — a 410 is a plain APIStatusError, so it crashed instead
of falling through. Result: 0 research for ~10 weeks behind a green workflow.

So: one shared chain, and ANY per-model API failure (404, 410, 429, 5xx,
timeout, connection) falls through to the next model. Only "every model
failed" is an error.

Usage (health probe — tries every model with a tiny prompt):
    export NVIDIA_API_KEY=nvapi-...
    python3 scripts/llm_client.py
"""

import os
import re
import sys
import time

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Ordered best-first. Only models that ANSWERED a probe with our key on
# 2026-11-02 (llm_health.yml). The catalog lists far more, but most 404 for a
# free key and several (deepseek-v4.1-flash, glm-5.3-flash, gpt-oss-20b,
# gemma-4-31b) timed out at 60s — a model that times out costs a full timeout
# per ticker before falling through, so it's worse than not listing it.
# Re-probe after any change: Actions → "LLM Model Health Check".
NVIDIA_CHAT_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b",      # flagship reasoning model, ~1.6s probe
    "mistralai/mistral-large-4-1t-a52b",      # strong independent fallback (slower, 17-34s)
    "minimaxai/minimax-m3.1-flash",           # fast, independent vendor
    "nvidia/nemotron-3.5-lightning-30b-a3b",  # small but quick last resort
    "stepfun-ai/step-5-preview",              # preview — may vanish, so last
]

MAX_STREAM_SECONDS = 240      # one model may write for this long
CHAT_DEADLINE_SECONDS = 480   # no new model starts after this, so a ticker can't eat the run

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _stream(client, model: str, messages: list[dict], max_tokens: int, temperature: float) -> str:
    """Full text of one completion. Raises ValueError if unusable.

    Streaming, because the client timeout then means "no data for that long". Without
    it a 90s timeout killed any model still writing, so at busy times every model failed.
    """
    started = time.monotonic()
    parts, finish_reason = [], None
    for chunk in client.chat.completions.create(model=model, messages=messages, stream=True,
                                                max_tokens=max_tokens, temperature=temperature):
        if time.monotonic() - started > MAX_STREAM_SECONDS:
            raise ValueError("too slow")
        if chunk.choices:
            parts.append(chunk.choices[0].delta.content or "")
            finish_reason = chunk.choices[0].finish_reason or finish_reason
    # Reasoning models may inline their scratchpad; never let it reach the UI.
    text = _THINK_RE.sub("", "".join(parts)).strip()
    if not text:
        raise ValueError("empty completion")
    # A note cut off at the token limit loses its verdict lines, which
    # are the last thing it writes.
    if finish_reason == "length":
        raise ValueError("truncated completion")
    return text


def chat(api_key: str, messages: list[dict], *, max_tokens: int,
         temperature: float = 0.3, timeout: float = 90,
         models: list[str] | None = None) -> tuple[str, str]:
    """Return (text, model_used). Raises RuntimeError only if every model fails."""
    import httpx
    from openai import APIError, OpenAI

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key,
                    timeout=timeout, max_retries=0)
    deadline = time.monotonic() + CHAT_DEADLINE_SECONDS
    last_err = None
    for model in models or NVIDIA_CHAT_MODELS:
        if time.monotonic() > deadline:
            print("   out of time for this request — not trying more models")
            break
        try:
            return _stream(client, model, messages, max_tokens, temperature), model
        # httpx errors surface raw when a stream drops part-way.
        except (APIError, httpx.HTTPError, ValueError) as exc:
            last_err = exc
            detail = getattr(exc, "status_code", None) or str(exc)[:60]
            print(f"   {model} failed ({type(exc).__name__}: {detail}) — trying next...")
    raise RuntimeError(f"All NVIDIA models failed. Last error: {last_err}")


def _probe():
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        print("❌ NVIDIA_API_KEY not set")
        sys.exit(1)
    # PROBE_MODELS="a,b,c" tests candidates without editing the chain.
    models = [m.strip() for m in os.environ.get("PROBE_MODELS", "").split(",") if m.strip()]
    models = models or NVIDIA_CHAT_MODELS
    ok = 0
    msgs = [{"role": "user", "content": "Reply with exactly: VERDICT: WATCHLIST"}]
    for model in models:
        t0 = time.time()
        try:
            text, _ = chat(key, msgs, max_tokens=200, timeout=60, models=[model])
            ok += 1
            print(f"✅ {model:45s} {time.time()-t0:5.1f}s  {text[:60]!r}")
        except RuntimeError as exc:
            print(f"❌ {model:45s} {time.time()-t0:5.1f}s  {str(exc)[-120:]}")
    print(f"\n{ok}/{len(models)} models answering")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _probe()
