import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import arxiv
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

import cache


# --- OpenAlex (primary) -----------------------------------------------------

OPENALEX_BASE = "https://api.openalex.org/works"
ARXIV_SOURCE_ID = "S4306400194"  # arXiv's source id in OpenAlex


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _openalex_search_raw(topic: str, per_page: int, from_date: str) -> dict:
    params = {
        "search": topic,
        "filter": f"primary_location.source.id:{ARXIV_SOURCE_ID},from_publication_date:{from_date}",
        "sort": "publication_date:desc",
        "per-page": min(max(per_page, 1), 200),
    }
    resp = requests.get(OPENALEX_BASE, params=params, timeout=20)
    if resp.status_code == 429:
        raise RuntimeError("OpenAlex rate limited")
    resp.raise_for_status()
    return resp.json()


def _reconstruct_abstract(inv_idx: Optional[dict]) -> str:
    if not inv_idx:
        return ""
    positions = sorted((i, w) for w, idxs in inv_idx.items() for i in idxs)
    return " ".join(w for _, w in positions)


def _arxiv_id_from_openalex(work: dict) -> Optional[str]:
    # arxiv works in OpenAlex carry an arxiv DOI like
    # "https://doi.org/10.48550/arxiv.2605.06330" (case varies). Extract the suffix.
    candidates = [
        work.get("doi"),
        (work.get("ids") or {}).get("doi"),
        (work.get("ids") or {}).get("arxiv"),
        (work.get("primary_location") or {}).get("landing_page_url"),
    ]
    for raw in candidates:
        if not raw:
            continue
        low = raw.lower()
        if "arxiv." in low:
            tail = low.split("arxiv.")[-1]
            return tail.rstrip("/").split("/")[-1].split("v")[0]
        if "/abs/" in low:
            return low.split("/abs/")[-1].rstrip("/").split("v")[0]
    return None


def _openalex_to_paper(work: dict, now: datetime) -> Optional[dict]:
    arxiv_id = _arxiv_id_from_openalex(work)
    if not arxiv_id:
        return None
    pub_date_str = work.get("publication_date") or "1970-01-01"
    try:
        pub_date = datetime.fromisoformat(pub_date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    age_days = max((now - pub_date).days, 1)
    primary_loc = work.get("primary_location") or {}
    pdf_url = primary_loc.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}"
    title = (work.get("title") or work.get("display_name") or "").strip()
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "authors": [
            (a.get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])
        ],
        "published": pub_date.isoformat(),
        "pdf_url": pdf_url,
        "age_days": age_days,
        "citation_count": work.get("cited_by_count"),
        "source": "openalex",
    }


def _search_via_openalex(topic: str, max_results: int, days_back: int) -> list[dict]:
    from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    # OpenAlex filters by date server-side, so no client-side over-fetch needed.
    data = _openalex_search_raw(topic, per_page=max_results, from_date=from_date)
    now = datetime.now(timezone.utc)
    papers: list[dict] = []
    for work in data.get("results", []):
        p = _openalex_to_paper(work, now)
        if p is None or not p["abstract"]:
            continue
        papers.append(p)
        if len(papers) >= max_results:
            break
    return papers


# --- arXiv (fallback) -------------------------------------------------------

# Reused so arxiv's internal delay/retry tracking persists across calls.
# Modest retry budget — arxiv is the fallback path now (OpenAlex is primary),
# so we want failures to surface quickly rather than burn 25s on retries.
_arxiv_client = arxiv.Client(page_size=20, delay_seconds=3.0, num_retries=2)


def _arxiv_search_raw(query: str, max_results: int):
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    return list(_arxiv_client.results(search))


def _build_arxiv_query(topic: str, category_query: str) -> str:
    if category_query:
        return f"({category_query}) AND ({topic})"
    return topic


def _search_via_arxiv(topic: str, max_results: int, days_back: int, category_query: str) -> list[dict]:
    full_query = _build_arxiv_query(topic, category_query)
    raw = _arxiv_search_raw(full_query, max_results=max_results * 3)
    now = datetime.now(timezone.utc)
    papers: list[dict] = []
    for r in raw:
        published = r.published
        age_days = max((now - published).days, 1)
        if age_days > days_back:
            continue
        arxiv_id = r.entry_id.split("/abs/")[-1].split("v")[0]
        papers.append({
            "arxiv_id": arxiv_id,
            "title": r.title.strip().replace("\n", " "),
            "abstract": r.summary.strip().replace("\n", " "),
            "authors": [a.name for a in r.authors],
            "published": published.isoformat(),
            "pdf_url": r.pdf_url,
            "age_days": age_days,
            "citation_count": None,
            "source": "arxiv",
        })
        if len(papers) >= max_results:
            break
    return papers


# --- Public API: search_papers (OpenAlex first, arxiv fallback) -------------


def search_papers(
    topic: str,
    max_results: int = 10,
    days_back: int = 365,
    category_query: str = "",
) -> list[dict]:
    cache_key = f"papers::{topic}::{category_query}::{max_results}::{days_back}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Primary: OpenAlex (high rate limit, citations included)
    try:
        papers = _search_via_openalex(topic, max_results, days_back)
        if papers:
            cache.set(cache_key, papers)
            return papers
        print("[openalex] returned zero results, falling back to arxiv")
    except Exception as e:
        print(f"[openalex] failed, falling back to arxiv: {type(e).__name__}: {e}")

    # Fallback: arxiv (exception propagates if this also fails)
    papers = _search_via_arxiv(topic, max_results, days_back, category_query)
    if papers:
        cache.set(cache_key, papers)
    return papers


# --- Semantic Scholar (citation backfill for arxiv-fallback path only) ------

S2_API = "https://api.semanticscholar.org/graph/v1/paper/ARXIV:{arxiv_id}"
S2_FIELDS = "citationCount,influentialCitationCount,publicationDate"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
def _s2_fetch_raw(arxiv_id: str) -> Optional[dict]:
    url = S2_API.format(arxiv_id=arxiv_id)
    resp = requests.get(url, params={"fields": S2_FIELDS}, timeout=15)
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("S2 rate limited")
    resp.raise_for_status()
    return resp.json()


def fetch_citation_counts(arxiv_ids: list[str]) -> dict[str, Optional[dict]]:
    out: dict[str, Optional[dict]] = {}
    for aid in arxiv_ids:
        cache_key = f"s2::{aid}"
        cached = cache.get(cache_key)
        if cached is not None:
            out[aid] = cached
            continue
        try:
            data = _s2_fetch_raw(aid)
        except Exception as e:
            print(f"[s2] failed for {aid}: {e}")
            data = None
        out[aid] = data
        if data is not None:
            cache.set(cache_key, data)
        time.sleep(0.5)
    return out


# --- Trending score ---------------------------------------------------------


def compute_trending_score(paper: dict) -> float:
    # citations dominate for older papers; the +1 keeps recency as a tiebreaker
    # for fresh papers that all have 0 citations.
    age_days = max(paper.get("age_days", 1), 1)
    cc = paper.get("citation_count") or 0
    return (cc + 1) / age_days
