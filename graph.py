import os
from typing import TypedDict

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

import tools
import prompts

MODEL = "llama-3.3-70b-versatile" #"llama-3.1-8b-instant"
TOP_N = 2
RANK_POOL = 5


class GraphState(TypedDict):
    topic: str
    category_query: str
    papers: list[dict]
    top_papers: list[dict]
    current_paper_index: int
    paper_analysis: str
    results: list[dict]
    final_report: str
    error: str


def _llm(temperature: float, max_tokens: int) -> ChatGroq:
    return ChatGroq(
        model=MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=os.environ.get("GROQ_API_KEY"),
    )


def search_arxiv_node(state: GraphState) -> dict:
    try:
        papers = tools.search_papers(
            state["topic"],
            max_results=10,
            days_back=365,
            category_query=state.get("category_query", ""),
        )
        return {"papers": papers}
    except Exception as e:
        return {
            "papers": [],
            "error": f"Paper search failed: {type(e).__name__}: {e}",
        }


def rank_trending_node(state: GraphState) -> dict:
    pool = state["papers"][:RANK_POOL]
    if not pool:
        return {"top_papers": [], "current_paper_index": 0, "results": []}

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
    return {"top_papers": top, "current_paper_index": 0, "results": []}


def analyze_paper_node(state: GraphState) -> dict:
    paper = state["top_papers"][state["current_paper_index"]]
    llm = _llm(temperature=0.4, max_tokens=4500)
    msg = prompts.COMBINED_PROMPT.format(title=paper["title"], abstract=paper["abstract"])
    resp = llm.invoke([HumanMessage(content=msg)])

    new_result = {
        "title": paper["title"],
        "arxiv_id": paper["arxiv_id"],
        "pdf_url": paper["pdf_url"],
        "published": paper.get("published", ""),
        "venue": paper.get("venue"),
        "analysis": resp.content,
    }
    return {
        "paper_analysis": resp.content,
        "results": state["results"] + [new_result],
        "current_paper_index": state["current_paper_index"] + 1,
    }


def synthesize_report_node(state: GraphState) -> dict:
    if state.get("error"):
        return {
            "final_report": (
                f"# Request failed\n\n"
                f"**{state['error']}**\n\n"
                "This is usually transient (rate limit or network blip). "
                "Wait a minute and try again."
            )
        }
    if not state["results"]:
        return {
            "final_report": (
                f"# No papers found for '{state['topic']}'\n\n"
                "Try a broader topic, or check your network connection."
            )
        }

    parts = [f"# GapScope Report: {state['topic']}\n"]
    for i, r in enumerate(state["results"], 1):
        parts.append(f"## Paper {i}: {r['title']}\n")
        meta_bits: list[str] = []
        pub = (r.get("published") or "").split("T")[0]
        if pub:
            meta_bits.append(f"**Published:** {pub}")
        if r.get("venue"):
            meta_bits.append(f"**Venue:** {r['venue']}")
        meta_bits.append(f"**arXiv:** [{r['arxiv_id']}]({r['pdf_url']})")
        parts.append(" &nbsp;·&nbsp; ".join(meta_bits) + "\n")
        parts.append(r["analysis"])
        parts.append("\n---\n")
    return {"final_report": "\n".join(parts)}


def _has_papers(state: GraphState) -> str:
    return "continue" if state["top_papers"] else "done"


def _more_papers(state: GraphState) -> str:
    return "continue" if state["current_paper_index"] < len(state["top_papers"]) else "done"


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("search", search_arxiv_node)
    graph.add_node("rank", rank_trending_node)
    graph.add_node("analyze_paper", analyze_paper_node)
    graph.add_node("synthesize", synthesize_report_node)

    graph.set_entry_point("search")
    graph.add_edge("search", "rank")
    graph.add_conditional_edges(
        "rank", _has_papers, {"continue": "analyze_paper", "done": "synthesize"}
    )
    graph.add_conditional_edges(
        "analyze_paper",
        _more_papers,
        {"continue": "analyze_paper", "done": "synthesize"},
    )
    graph.add_edge("synthesize", END)
    return graph.compile()


compiled_graph = build_graph()
