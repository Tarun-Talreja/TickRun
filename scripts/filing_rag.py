#!/usr/bin/env python3
"""
scripts/filing_rag.py — Answer questions from a company's actual 10-K.

Every research note ends with "three things to verify in the 10-K" — and until
now you had to go read it yourself. This closes that loop: it fetches the real
filing from SEC EDGAR, retrieves the passages that bear on a question, and
answers with those passages quoted as evidence.

WHY RETRIEVAL RATHER THAN JUST PASTING THE FILING IN
A 10-K runs 100k-500k+ tokens. The models available here top out well below
that, and even a large window would bury the relevant paragraph in noise and
cost. So: chunk the filing, embed the chunks, and send only the handful that
actually match the question. That is the entire point of RAG.

MODEL CONSTRAINTS THIS IS BUILT AROUND
  - Embedding inputs are capped (commonly 512 tokens), so chunks stay small
    with overlap to avoid cutting a sentence's meaning in half.
  - Free-tier rate limits are real, so chunks are batched, capped, and cached
    to disk. A 10-K is annual — re-running should cost nothing.
  - A listed model is not necessarily a provisioned one (the 253B taught us
    that), so embedding runs through a fallback chain and, if every hosted
    model is unavailable, degrades to local TF-IDF retrieval that needs no API
    at all. Retrieval quality drops; the feature does not disappear.

Usage:
    python3 scripts/filing_rag.py --probe                 # which models work?
    python3 scripts/filing_rag.py TLN                     # default questions
    python3 scripts/filing_rag.py TLN --question "What is the customer concentration?"
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

try:
    import numpy as np
    import requests
except ImportError:
    print("Missing dependency: pip install numpy requests")
    sys.exit(1)

SCRIPT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR    = os.path.join(SCRIPT_DIR, "data", "filing_cache")
OUTPUT_DIR   = os.path.join(SCRIPT_DIR, "output", "filing_answers")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS     = {"User-Agent": "TickRun Research tarun888099@gmail.com"}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

# Preferred first: nv-embedqa-e5-v5 is tuned for question-answering retrieval,
# which is exactly this task. Others are general-purpose fallbacks.
EMBED_MODEL_CHAIN = [
    "nvidia/nv-embedqa-e5-v5",
    "nvidia/llama-3.2-nv-embedqa-1b-v1",
    "baai/bge-m3",
    "snowflake/arctic-embed-l",
]
ANSWER_MODEL = "meta/llama-3.3-70b-instruct"

CHUNK_WORDS   = 350    # ~450-500 tokens, safely inside the 512-token embed cap
CHUNK_OVERLAP = 60     # keeps a claim from being split across a boundary
MAX_CHUNKS    = 320    # rate-limit / runtime guard on very long filings
EMBED_BATCH   = 32
TOP_K         = 4     # smaller context -> answer calls that finish in time

DEFAULT_QUESTIONS = [
    "What are the most significant risk factors disclosed?",
    "What is the customer concentration — do any customers exceed 10% of revenue?",
    "What are the debt maturities and total debt obligations?",
]


# ── SEC fetch ────────────────────────────────────────────────────────────────

def _cik_for(ticker: str) -> str | None:
    data = requests.get(TICKERS_URL, headers=HEADERS, timeout=30).json()
    for v in data.values():
        if v["ticker"].upper() == ticker.upper():
            return str(v["cik_str"]).zfill(10)
    return None


def _latest_annual_filing(cik: str) -> dict | None:
    """Most recent 10-K (or 20-F for foreign issuers like ASML/TSM)."""
    sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                       headers=HEADERS, timeout=30).json()
    r = sub.get("filings", {}).get("recent", {})
    for i, form in enumerate(r.get("form", [])):
        if form in ("10-K", "20-F"):
            acc = r["accessionNumber"][i].replace("-", "")
            return {
                "form": form,
                "date": r["filingDate"][i],
                "accession": acc,
                "url": (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                        f"{acc}/{r['primaryDocument'][i]}"),
            }
    return None


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    for ent, ch in (("&nbsp;", " "), ("&amp;", "&"), ("&#8217;", "'"),
                    ("&#8220;", '"'), ("&#8221;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(ent, ch)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _chunk(text: str) -> list[str]:
    words, chunks, i = text.split(), [], 0
    step = CHUNK_WORDS - CHUNK_OVERLAP
    while i < len(words) and len(chunks) < MAX_CHUNKS:
        c = " ".join(words[i:i + CHUNK_WORDS])
        if len(c) > 200:                      # skip boilerplate/whitespace fragments
            chunks.append(c)
        i += step
    return chunks


# ── Embeddings, with graceful degradation ────────────────────────────────────

def _embed(texts: list[str], api_key: str, input_type: str,
           pin_model: str | None = None) -> tuple[np.ndarray | None, str | None]:
    """Embed texts, returning (vectors, model_used).

    pin_model forces a specific model and disables the fallback chain. Query
    vectors and passage vectors must come from the same model — different
    embedders produce different vector spaces, so mixing them would make cosine
    similarity meaningless while still returning plausible-looking numbers.
    This is defensive rather than a fix for an observed bug: in practice the
    fallback chain settled on the same model for both, but a transient 503 on
    the first choice could silently split them, and that failure mode is very
    hard to spot from the output.
    """
    try:
        from openai import OpenAI
    except ImportError:
        return None, None
    client = OpenAI(base_url=NVIDIA_BASE, api_key=api_key, timeout=90, max_retries=3)

    candidates = [pin_model] if pin_model else EMBED_MODEL_CHAIN
    for model in candidates:
        vectors = []
        try:
            for i in range(0, len(texts), EMBED_BATCH):
                batch = texts[i:i + EMBED_BATCH]
                # NVIDIA retrieval embedders use asymmetric query/passage
                # encoding; extra_body is ignored by models that don't use it.
                for attempt in range(4):
                    try:
                        resp = client.embeddings.create(
                            model=model, input=batch,
                            extra_body={"input_type": input_type, "truncate": "END"},
                        )
                        break
                    except Exception as e:
                        # Free-tier concurrency limits surface as 503/429 under
                        # load; back off rather than dropping to another model.
                        if attempt == 3 or not any(c in str(e) for c in ("503", "429", "ResourceExhausted")):
                            raise
                        time.sleep(2 ** attempt)
                vectors.extend(d.embedding for d in resp.data)
                time.sleep(1.0)               # pace against free-tier limits
            return np.array(vectors, dtype=float), model
        except Exception as e:
            if pin_model:
                print(f"   ✗ pinned embedder {model} failed ({str(e)[:80]})")
                return None, None
            print(f"   embed via {model} unavailable ({str(e)[:70]}) — trying next")
            continue
    return None, None


def _tfidf(chunks: list[str], query: str) -> np.ndarray:
    """Local fallback: no API, no network. Weaker than embeddings but keeps the
    feature working when no hosted embedder is provisioned."""
    def toks(s): return re.findall(r"[a-z0-9]+", s.lower())
    docs = [toks(c) for c in chunks]
    vocab = {}
    for d in docs:
        for t in set(d):
            vocab.setdefault(t, len(vocab))
    N = len(docs)
    df = np.zeros(len(vocab))
    for d in docs:
        for t in set(d):
            df[vocab[t]] += 1
    idf = np.log((N + 1) / (df + 1)) + 1.0

    def vec(tokens):
        v = np.zeros(len(vocab))
        for t in tokens:
            if t in vocab:
                v[vocab[t]] += 1
        v *= idf
        n = np.linalg.norm(v)
        return v / n if n else v

    D = np.array([vec(d) for d in docs])
    q = vec(toks(query))
    return D @ q


def _retrieve(chunks, chunk_vecs, query, api_key, k=TOP_K, index_model=None):
    if chunk_vecs is not None and index_model:
        # Pin to the model that built the index — a query embedded by any other
        # model lands in a different vector space and the scores become noise.
        qv, _ = _embed([query], api_key, "query", pin_model=index_model)
        if qv is not None:
            sims = chunk_vecs @ qv[0] / (
                np.linalg.norm(chunk_vecs, axis=1) * np.linalg.norm(qv[0]) + 1e-9)
            idx = np.argsort(-sims)[:k]
            return [(chunks[i], float(sims[i])) for i in idx], "embeddings"
        print("   ⚠ query embedding failed — falling back to TF-IDF for this query")
    sims = _tfidf(chunks, query)
    idx = np.argsort(-sims)[:k]
    return [(chunks[i], float(sims[i])) for i in idx], "tfidf"


# ── Answering ────────────────────────────────────────────────────────────────

def _answer(question, passages, ticker, filing, api_key) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return "openai package unavailable."
    # Cap each passage: the free-tier endpoint times out on long prompts, and
    # the answer only needs the relevant span, not the whole chunk.
    ctx = "\n\n".join(f"[Passage {i+1}]\n{p[:1200]}" for i, (p, _) in enumerate(passages))
    prompt = (
        f"You are reading {ticker}'s {filing['form']} filed {filing['date']}. "
        f"Answer the question using ONLY the passages below.\n\n"
        f"Rules:\n"
        f"- Quote the specific language that supports your answer.\n"
        f"- If the passages do not contain the answer, say exactly: "
        f"'Not found in the retrieved passages.' Do not use outside knowledge.\n"
        f"- Be concise and specific. Prefer numbers over adjectives.\n\n"
        f"QUESTION: {question}\n\n{ctx}"
    )
    try:
        client = OpenAI(base_url=NVIDIA_BASE, api_key=api_key, timeout=180, max_retries=2)
        r = client.chat.completions.create(
            model=ANSWER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=450, temperature=0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"Answer generation failed: {e}"


# ── Cache ────────────────────────────────────────────────────────────────────

def _cache_path(ticker, accession, kind):
    return os.path.join(CACHE_DIR, f"{ticker}_{accession}_{kind}")


def _load_or_build_chunks(ticker, filing):
    p = _cache_path(ticker, filing["accession"], "chunks.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    print(f"   fetching filing ({filing['form']} {filing['date']})...")
    html = requests.get(filing["url"], headers=HEADERS, timeout=90).text
    chunks = _chunk(_html_to_text(html))
    with open(p, "w") as f:
        json.dump(chunks, f)
    return chunks


def _load_or_build_vecs(ticker, filing, chunks, api_key):
    p = _cache_path(ticker, filing["accession"], "vecs.npy")
    m = _cache_path(ticker, filing["accession"], "model.txt")
    if os.path.exists(p):
        return np.load(p), open(m).read().strip() if os.path.exists(m) else "cached"
    if not api_key:
        return None, None
    print(f"   embedding {len(chunks)} chunks...")
    vecs, model = _embed(chunks, api_key, "passage")
    if vecs is not None:
        np.save(p, vecs)
        with open(m, "w") as f:
            f.write(model)
    return vecs, model


# ── Main ─────────────────────────────────────────────────────────────────────

def _probe(api_key):
    print("Probing embedding models on this key...\n")
    for model in EMBED_MODEL_CHAIN:
        v, used = _embed(["test passage about revenue concentration"], api_key, "passage")
        if v is not None:
            print(f"\n✅ WORKING: {used}  (dim={v.shape[1]})")
            return
    print("\n⚠ No hosted embedder available — retrieval will use local TF-IDF.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?", help="Ticker, e.g. TLN")
    ap.add_argument("--question", action="append", help="Custom question (repeatable)")
    ap.add_argument("--probe", action="store_true", help="Test which embedders work")
    args = ap.parse_args()

    api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if args.probe:
        if not api_key:
            print("No NVIDIA_API_KEY set.")
            sys.exit(0)
        _probe(api_key)
        return

    if not args.ticker:
        ap.error("ticker required (or use --probe)")
    ticker = args.ticker.upper()

    cik = _cik_for(ticker)
    if not cik:
        print(f"No CIK for {ticker} (ADR/ETF without SEC registration?)")
        sys.exit(0)
    filing = _latest_annual_filing(cik)
    if not filing:
        print(f"No 10-K/20-F found for {ticker}.")
        sys.exit(0)

    print(f"📄 {ticker} — {filing['form']} filed {filing['date']}")
    chunks = _load_or_build_chunks(ticker, filing)
    print(f"   {len(chunks)} chunks")

    vecs, model = _load_or_build_vecs(ticker, filing, chunks, api_key)
    print(f"   retrieval: {'embeddings via ' + model if vecs is not None else 'local TF-IDF (no embedder)'}")

    questions = args.question or DEFAULT_QUESTIONS
    results = []
    for q in questions:
        print(f"\n❓ {q}")
        passages, method = _retrieve(chunks, vecs, q, api_key, index_model=model)
        ans = _answer(q, passages, ticker, filing, api_key) if api_key else \
              "(no API key — retrieved passages only)"
        print(f"   [{method}] {ans[:400]}")
        results.append({
            "question": q, "answer": ans, "retrieval_method": method,
            "passages": [{"text": p[:600], "score": round(s, 3)} for p, s in passages],
        })
        time.sleep(2)   # pace answer calls against free-tier concurrency limits

    out = {
        "ticker": ticker, "filing": filing,
        "retrieval": f"embeddings:{model}" if vecs is not None else "tfidf",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
    }
    path = os.path.join(OUTPUT_DIR, f"{ticker}_{filing['date']}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n✅ Saved → {path}")


if __name__ == "__main__":
    main()
