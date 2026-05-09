---
title: GapScope
colorFrom: indigo
colorTo: green
sdk: gradio
sdk_version: 6.14.0
app_file: app.py
pinned: false
---

# GapScope

A Gradio app that searches recent arXiv papers on a topic, ranks them by a trending score, and uses Groq-hosted Llama 3.3 70B to summarize each paper, identify research gaps, and propose novel research directions.

## How it works

1. User enters a topic (e.g. *"efficient fine-tuning of LLMs"*)
2. `search_papers` queries **OpenAlex** for recent arXiv papers (last 365 days) — citation counts come back in the same call. Falls back to arXiv's API if OpenAlex is unavailable
3. For papers missing citation data (arXiv-fallback path only), Semantic Scholar fills the gap
4. Papers are ranked by `citation_count / age_days` (approximation of trending score)
5. The top 2 papers are each run through a 3-step LLM pipeline:
   - **Summary** (temp 0.3) — structured bullets covering problem, method, contribution, and key results
   - **Gap analysis** (temp 0.3) — three concrete research gaps
   - **Idea generation** (temp 0.7) — two novel research directions per paper
6. A consolidated markdown report is rendered in the Gradio UI

The orchestration is a LangGraph state machine with conditional edges that loop the per-paper pipeline.

## Tech stack

- **UI:** Gradio
- **Agent orchestration:** LangGraph
- **LLM:** Groq (`llama-3.3-70b-versatile`) via `langchain-groq`
- **Data sources:** OpenAlex (primary), arXiv (fallback via `arxiv` library), Semantic Scholar (citation backfill when arxiv fallback is used)
- **Reliability:** `tenacity` retries with exponential backoff, JSON cache (7-day TTL)

## Local setup

```powershell
# clone the repo, then:
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# add your Groq API key to .env
# GROQ_API_KEY=gsk_...

python app.py
```

The app will open at `http://127.0.0.1:7860`.

Get a free Groq API key at https://console.groq.com.

## Deploy to Hugging Face Spaces

1. Create a new Space with the **Gradio** SDK
2. Push the repo (everything except `.env`, `cache.json`, `venv/`, and `__pycache__/`)
3. Add `GROQ_API_KEY` under **Settings → Repository secrets**
4. The Space will auto-install from `requirements.txt` and launch `app.py`

## Project structure

```
app.py            Gradio interface, progress tracking, error handling
graph.py          LangGraph state and 6 nodes (search, rank, summarize, gap, ideas, synthesize)
tools.py          arXiv + Semantic Scholar clients with retries and caching
prompts.py        SUMMARY / GAP / IDEA prompt templates
cache.py          JSON cache with 7-day TTL
requirements.txt  Pinned dependencies
.env              Local secrets (do not commit)
.gitignore        Ignores .env, cache.json, venv, __pycache__
```

## Demo

*(Screenshot placeholder — capture the UI after running a query and embed `demo.png` here.)*

## Output quality notes

**Strengths**
- Recency-biased: only papers from the last 365 days, so the report reflects what is genuinely trending
- Structured output: every section uses fixed markdown templates, so the report is easy to scan
- Cheap: ~6 LLM calls per run (3 per paper × 2 papers), all on the Groq free tier

**Weaknesses / known limits**
- The trending score uses `citationCount / age_days` as a proxy for `citations_last_30d / age_days`. Semantic Scholar does not expose a 30-day delta cheaply, so very fresh papers (where citations have not yet caught up) may be under-ranked relative to slightly older papers
- Gap and idea quality is bounded by the abstract — the agent does not read full PDFs, so methodological nuances inside the paper body can be missed
- The agent can occasionally invent plausible-sounding but unstated results; the prompt warns against this but does not eliminate it
- Semantic Scholar rate-limits aggressively on the free tier; on persistent failure the ranker falls back to pure date sorting and the report still produces

## Cost

Groq free tier covers all LLM calls. arXiv and Semantic Scholar are free. Total external cost per run: $0.
