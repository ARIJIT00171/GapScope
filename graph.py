import os
from typing import TypedDict

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

import tools
import prompts

MODEL = "llama-3.3-70b-versatile"  # "llama-3.1-8b-instant" for testing
TOP_N = 5  # papers shown in the selection list


class SearchState(TypedDict):
    topic: str
    category_query: str
    openalex_concept: str
    papers: list[dict]
    top_papers: list[dict]
    error: str


class AnalyzeState(TypedDict):
    topic: str
    paper: dict
    analysis: str
    final_report: str


def _llm(temperature: float, max_tokens: int) -> ChatGroq:
    return ChatGroq(
        model=MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=os.environ.get("GROQ_API_KEY"),
    )


def search_node(state: SearchState) -> dict:
    try:
        papers = tools.search_papers(
            state["topic"],
            max_results=10,
            days_back=365,
            category_query=state.get("category_query", ""),
            openalex_concept=state.get("openalex_concept", ""),
        )
        return {"papers": papers}
    except Exception as e:
        return {
            "papers": [],
            "error": f"Paper search failed: {type(e).__name__}: {e}",
        }


def rank_node(state: SearchState) -> dict:
    pool = state["papers"][:10]
    if not pool:
        return {"top_papers": []}

    # Backfill citation_count via Semantic Scholar only for papers missing it
    # (i.e. the arxiv-fallback path; OpenAlex returns citations directly).
    missing = [p for p in pool if p.get("citation_count") is None]
    if missing:
        cite_data = tools.fetch_citation_counts([p["arxiv_id"] for p in missing])
        for p in missing:
            cd = cite_data.get(p["arxiv_id"])
            p["citation_count"] = cd.get("citationCount") if cd else None

    scored = [(tools.compute_trending_score(p), p) for p in pool]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[:TOP_N]]
    return {"top_papers": top}


def analyze_node(state: AnalyzeState) -> dict:
    paper = state["paper"]
    llm = _llm(temperature=0.4, max_tokens=4500)
    msg = prompts.COMBINED_PROMPT.format(title=paper["title"], abstract=paper["abstract"])
    resp = llm.invoke([HumanMessage(content=msg)])
    return {"analysis": resp.content}


def synthesize_node(state: AnalyzeState) -> dict:
    paper = state["paper"]
    parts = [f"# GapScope Report: {state['topic']}\n"]
    parts.append(f"## {paper['title']}\n")
    meta_bits: list[str] = []
    pub = (paper.get("published") or "").split("T")[0]
    if pub:
        meta_bits.append(f"**Published:** {pub}")
    if paper.get("venue"):
        meta_bits.append(f"**Venue:** {paper['venue']}")
    cc = paper.get("citation_count")
    if cc is not None and cc > 0:
        meta_bits.append(f"**Citations:** {cc}")
    meta_bits.append(f"**arXiv:** [{paper['arxiv_id']}]({paper['pdf_url']})")
    parts.append(" &nbsp;·&nbsp; ".join(meta_bits) + "\n")
    parts.append(state["analysis"])
    return {"final_report": "\n".join(parts)}


def build_search_graph():
    g = StateGraph(SearchState)
    g.add_node("search", search_node)
    g.add_node("rank", rank_node)
    g.set_entry_point("search")
    g.add_edge("search", "rank")
    g.add_edge("rank", END)
    return g.compile()


def build_analyze_graph():
    g = StateGraph(AnalyzeState)
    g.add_node("analyze", analyze_node)
    g.add_node("synthesize", synthesize_node)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


search_rank_graph = build_search_graph()
analyze_one_graph = build_analyze_graph()
