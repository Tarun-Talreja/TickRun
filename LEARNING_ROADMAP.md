# AI Engineer Roadmap — what's left, mapped to what you already did

You built TickRun. That means you already have **real reps** with patterns most
people only read about. This roadmap starts from there and shows what's left.

---

## ✅ What you already learned (don't undersell this)

| Concept | Where you did it in TickRun |
|---------|----------------------------|
| RAG (retrieval-augmented generation) | Feeding news + fundamentals into the research prompt |
| Grounding / anti-hallucination | "Say unverified if not in the data" |
| Structured output + parsing | Forcing `VERDICT:` / `CONFIDENCE:` lines, regex extraction |
| Model fallback / graceful degradation | 253B → 70B chain |
| Adversarial / multi-pass prompting | The bear-case second pass |
| Prompt iteration / debugging | Fixing the model that wrote prose with no verdict |
| Evaluation (early) | `track_record.py` scoring past calls |
| Cost/latency awareness | Free-tier limits, model routing |

This is genuinely ~40% of practical "AI engineering." The rest is below.

---

## 🧰 On LangChain (and friends) — the honest version

**What it is:** a framework that wraps LLM calls, prompts, retrieval, memory, and
"chains"/agents behind common abstractions. Siblings: **LlamaIndex** (retrieval-focused),
**LangGraph** (stateful agent graphs), **Haystack**, and lighter tools like **DSPy**
and **Instructor** (structured output).

**The honest take for someone at your stage:**
- You do **not** need LangChain to be an AI engineer. You've been calling the
  OpenAI-compatible SDK directly — that's exactly how many production teams ship,
  because frameworks add abstraction you must then debug *through*.
- **Learn the fundamentals first (you're doing this), then learn LangChain to know
  the vocabulary** — interviews and teams use its terms (retrievers, chains, agents,
  tool-calling, memory). Being able to say "this is just a retriever + a chain" is
  the value, not memorizing its API.
- For new code, many shops now prefer **the raw provider SDK + a thin structured-output
  lib (Instructor / Pydantic) + LangGraph only when they truly need stateful agents.**

**Practical move:** rebuild *one* TickRun piece (e.g. the research call) using
LangChain or LlamaIndex. You'll instantly see what it abstracts — and what it hides.

---

## 🗺️ The roadmap (in learning-value order)

### Tier 1 — Core LLM app skills (you're mostly here)
- [x] Prompt engineering: zero/few-shot, system prompts, output forcing
- [x] RAG basics: retrieve → ground → generate
- [ ] **Structured output done right** — JSON mode, function/tool schemas, Pydantic
      validation (libraries: **Instructor**, OpenAI structured outputs)
- [ ] **Token/cost/latency** — context windows, streaming, batching, caching

### Tier 2 — Retrieval that actually scales
- [ ] **Embeddings** — turn text into vectors; cosine similarity
- [ ] **Vector databases** — pgvector, Pinecone, Chroma, FAISS
- [ ] **Chunking & reranking** — how you split docs + reorder results for relevance
- [ ] *TickRun project:* embed news headlines, retrieve the most relevant per ticker
      (replaces today's keyword match)

### Tier 3 — Agents & tool use (the big one)
- [ ] **Tool/function calling** — the model decides which function to invoke
- [ ] **Agent loops** — plan → act → observe → repeat (ReAct pattern)
- [ ] **LangGraph / state machines** — controllable multi-step agents
- [ ] *TickRun project:* an agent that decides per ticker whether to pull the 10-K,
      check insider trades, or read news — instead of the fixed pipeline

### Tier 4 — Making it trustworthy & production-ready
- [ ] **Evaluation** — build an eval set, measure accuracy, catch regressions
      (tools: **Ragas**, **LangSmith**, **promptfoo**). You started with `track_record.py`.
- [ ] **Observability** — trace/log every LLM call, token usage, failures
- [ ] **Guardrails** — input/output validation, PII filtering, jailbreak defense
- [ ] **Caching & determinism** — prompt caching, temperature control, reproducibility

### Tier 5 — Deeper ML foundations (the moat)
- [ ] **How transformers work** — attention, tokens, embeddings (conceptual is enough first)
- [ ] **Fine-tuning vs RAG vs prompting** — when to use which
- [ ] **LoRA / PEFT** — cheap fine-tuning
- [ ] **Local models** — Ollama, llama.cpp, quantization
- [ ] **A little math** — vectors, probability, gradient descent (for depth/interviews)

---

## 🎯 Three projects that would take you far

1. **Embed + semantic search over filings** — pull a 10-K, chunk it, embed it,
   answer "what are the risk factors?" by retrieving the right chunks. (Teaches Tier 2.)
2. **A research agent** — give the model tools (get_news, get_filings, get_fundamentals)
   and let it decide what to call. (Teaches Tier 3 — the most marketable skill.)
3. **An eval harness** — take 20 past TickRun verdicts, label what actually happened,
   and score the model. Swap models/prompts and compare. (Teaches Tier 4 — what
   separates hobbyists from engineers.)

---

## 📚 Resources worth the time

- **Anthropic's "Building Effective Agents"** + prompt engineering docs
- **OpenAI cookbook** (structured outputs, function calling, evals)
- **DeepLearning.AI short courses** (RAG, agents, LangChain, evaluation) — free, ~1hr each
- **LangChain/LlamaIndex docs** — skim to learn vocabulary, don't memorize
- **"Designing Machine Learning Systems"** (Chip Huyen) — the production mindset

---

## The one-line summary

> You already write *grounded, structured, fault-tolerant* LLM code. What's left is:
> **retrieval at scale (embeddings/vector DBs), agents (tool-use loops), and evaluation.**
> LangChain is vocabulary to learn *after* the fundamentals — which you have.
> Build the three projects above and you're an AI engineer, not an aspiring one.
