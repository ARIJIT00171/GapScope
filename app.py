import os

from dotenv import load_dotenv
import gradio as gr

load_dotenv()

from graph import search_rank_graph, analyze_one_graph

FIELD_PRESETS: dict[str, dict[str, str]] = {
    "AI / ML (general)": {
        "arxiv": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.CV OR cat:stat.ML",
        "openalex_concept": "C154945302",  # Artificial intelligence
    },
    "NLP only": {
        "arxiv": "cat:cs.CL OR cat:cs.AI OR cat:cs.LG",
        "openalex_concept": "C204321447",  # Natural language processing
    },
    "Computer Vision only": {
        "arxiv": "cat:cs.CV OR cat:cs.AI OR cat:cs.LG",
        "openalex_concept": "C31972630",  # Computer vision
    },
    "Robotics": {
        "arxiv": "cat:cs.RO OR cat:cs.AI OR cat:cs.LG",
        "openalex_concept": "C90509273",  # Robotics
    },
    "Reinforcement Learning": {
        "arxiv": "cat:cs.LG OR cat:cs.AI OR cat:cs.MA",
        "openalex_concept": "C97541855",  # Reinforcement learning
    },
    "All CS": {"arxiv": "cat:cs.*", "openalex_concept": "C41008148"},  # Computer science
    "All categories (no filter)": {"arxiv": "", "openalex_concept": ""},
}
DEFAULT_PRESET = "AI / ML (general)"


def _radio_choices(papers: list[dict]) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for i, p in enumerate(papers, 1):
        pub = (p.get("published") or "").split("T")[0]
        meta: list[str] = []
        if pub:
            meta.append(pub)
        if p.get("venue"):
            meta.append(p["venue"])
        cc = p.get("citation_count")
        if cc is not None and cc > 0:
            meta.append(f"{cc} citations")
        meta.append(f"arXiv:{p['arxiv_id']}")
        meta_line = "  ·  ".join(meta)

        abstract = (p.get("abstract") or "").strip() or "(no abstract available)"
        label = f"{i}. {p['title']}\n\n{meta_line}\n\n{abstract}"
        choices.append((label, str(i)))
    return choices


SPINNER = "<span class='gs-spinner'></span>"


def _status(msg: str, spinning: bool = False) -> str:
    prefix = SPINNER if spinning else ""
    return f"<div class='gs-status'>{prefix}{msg}</div>"


def do_search(topic: str, field_preset: str):
    hide = gr.update(visible=False)
    if not topic or not topic.strip():
        yield _status("Please enter a research topic."), 0, [], hide, hide, ""
        return
    if not os.environ.get("GROQ_API_KEY") or os.environ["GROQ_API_KEY"].startswith("your_"):
        yield _status("<strong>Error:</strong> <code>GROQ_API_KEY</code> is not set. Add it to <code>.env</code> and restart."), 0, [], hide, hide, ""
        return

    topic = topic.strip()
    preset = FIELD_PRESETS.get(field_preset, FIELD_PRESETS[DEFAULT_PRESET])
    initial = {
        "topic": topic,
        "category_query": preset["arxiv"],
        "openalex_concept": preset["openalex_concept"],
        "papers": [],
        "top_papers": [],
        "error": "",
    }

    try:
        yield _status("Searching arXiv for recent papers...", spinning=True), 20, [], hide, hide, ""

        final_state = None
        for event in search_rank_graph.stream(initial, stream_mode="values"):
            final_state = event
            if event.get("error"):
                yield _status(f"<strong>Error:</strong> {event['error']}"), 100, [], hide, hide, ""
                return
            if event.get("papers") and not event.get("top_papers"):
                yield (
                    _status(f"Ranking {len(event['papers'])} papers...", spinning=True),
                    65, [], hide, hide, "",
                )

        top = (final_state or {}).get("top_papers", [])
        if not top:
            yield (
                _status("No papers found. Try a broader topic or a different field preset."),
                100, [], hide, hide, "",
            )
            return

        choices = _radio_choices(top)
        yield (
            _status(f"<strong>Found {len(top)} papers.</strong> Select one and click <em>Analyze selected paper</em>."),
            100,
            top,
            gr.update(choices=choices, value=choices[0][1], visible=True),
            gr.update(visible=True),
            "",
        )
    except Exception as e:
        yield _status(f"<strong>Error:</strong> {type(e).__name__}: {e}"), 100, [], hide, hide, ""


def do_analyze(selection: str, papers: list[dict], analyses_cache: dict, topic: str):
    if not papers:
        yield _status("Search for papers first."), 0, "", analyses_cache
        return
    if not selection:
        yield _status("Select a paper first."), 0, "", analyses_cache
        return

    try:
        idx = int(selection) - 1
    except (ValueError, TypeError):
        yield _status("Invalid selection."), 0, "", analyses_cache
        return
    if idx < 0 or idx >= len(papers):
        yield _status("Selection out of range."), 0, "", analyses_cache
        return

    paper = papers[idx]
    arxiv_id = paper["arxiv_id"]

    if arxiv_id in analyses_cache:
        yield _status("Loaded cached analysis."), 100, analyses_cache[arxiv_id], analyses_cache
        return

    yield (
        _status(f"<strong>Analyzing:</strong> <em>{paper['title']}</em>", spinning=True),
        30, "", analyses_cache,
    )

    try:
        initial = {"topic": topic.strip(), "paper": paper, "analysis": "", "final_report": ""}
        final_state = None
        for event in analyze_one_graph.stream(initial, stream_mode="values"):
            final_state = event
            if event.get("analysis") and not event.get("final_report"):
                yield _status("Synthesizing report...", spinning=True), 80, "", analyses_cache

        report = (final_state or {}).get("final_report", "")
        if not report:
            yield _status("No report produced."), 100, "", analyses_cache
            return
        new_cache = {**analyses_cache, arxiv_id: report}
        yield _status("<strong>Done.</strong>"), 100, report, new_cache
    except Exception as e:
        yield _status(f"<strong>Error:</strong> {type(e).__name__}: {e}"), 100, "", analyses_cache


theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="emerald",
    neutral_hue="slate",
)

CUSTOM_CSS = """
.gradio-container { max-width: 1100px !important; margin: 0 auto !important; }

#gs-header { text-align: center; padding: 18px 0 6px; }
#gs-header h1 {
    font-size: 2.4rem; font-weight: 700; letter-spacing: -0.02em;
    background: linear-gradient(90deg, #6366f1 0%, #10b981 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin: 0;
}

#gs-tagline {
    text-align: center;
    color: var(--body-text-color-subdued);
    margin: 4px 0 18px;
    font-size: 1rem;
}

#status-line {
    min-height: 1.5em;
    padding: 4px 0;
    color: var(--body-text-color);
    font-size: 0.95rem;
}
.gs-status {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--body-text-color);
    line-height: 1.5;
}
.gs-status code {
    background: var(--code-background-fill, rgba(125,125,125,0.15));
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.9em;
}

.gs-spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid var(--border-color-primary, rgba(125,125,125,0.3));
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: gs-spin 0.8s linear infinite;
    vertical-align: -2px;
    margin-right: 8px;
}
@keyframes gs-spin { to { transform: rotate(360deg); } }

#paper-radio { margin-top: 8px; }
#paper-radio .wrap, #paper-radio fieldset, #paper-radio > div {
    display: flex !important;
    flex-direction: column !important;
    gap: 12px !important;
}
#paper-radio label {
    display: flex !important;
    align-items: flex-start !important;
    gap: 12px !important;
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 14px 18px;
    margin: 0 !important;
    cursor: pointer;
    color: var(--body-text-color);
    line-height: 1.55;
    max-height: 260px;
    overflow-y: auto;
    transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
    white-space: pre-wrap;
    font-size: 0.95rem;
}
#paper-radio label:hover {
    border-color: #6366f1;
}
#paper-radio label:has(input:checked) {
    border-color: #6366f1;
    background: rgba(99, 102, 241, 0.08);
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.18);
}
#paper-radio label input[type="radio"] {
    margin-top: 4px;
    flex-shrink: 0;
    accent-color: #6366f1;
}
#paper-radio label span { white-space: pre-wrap !important; }

#report-card {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 24px 28px;
    margin-top: 12px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    color: var(--body-text-color);
}
#report-card h1 {
    font-size: 1.8rem;
    border-bottom: 2px solid var(--border-color-primary);
    padding-bottom: 6px;
}
#report-card h2 { font-size: 1.3rem; color: #6366f1; margin-top: 1.4em; }
#report-card h3 { font-size: 1.05rem; color: #14b8a6; margin-top: 1em; }
#report-card hr { border: none; border-top: 1px dashed var(--border-color-primary); margin: 1.6em 0; }
#report-card a { color: #6366f1; text-decoration: none; }
#report-card a:hover { text-decoration: underline; }

#mine-btn, #analyze-btn { min-height: 44px; }
"""

with gr.Blocks(title="GapScope", css=CUSTOM_CSS) as demo:
    gr.HTML("<div id='gs-header'><h1>GapScope</h1></div>")
    gr.HTML(
        "<div id='gs-tagline'>Find research gaps in trending arXiv papers — "
        "powered by OpenAlex, LangGraph, and Groq Llama 3.3 70B.</div>"
    )

    with gr.Row():
        topic_input = gr.Textbox(
            label="Research topic",
            placeholder="e.g. efficient fine-tuning of LLMs",
            scale=4,
        )
        field_preset = gr.Dropdown(
            choices=list(FIELD_PRESETS.keys()),
            value=DEFAULT_PRESET,
            label="Field",
            scale=2,
        )
        search_btn = gr.Button("Find papers", variant="primary", scale=1, elem_id="mine-btn")

    status = gr.HTML(value="", elem_id="status-line")
    progress_bar = gr.Slider(
        minimum=0, maximum=100, value=0, step=1,
        label="Progress (%)", interactive=False,
    )

    papers_state = gr.State([])
    analyses_state = gr.State({})

    paper_radio = gr.Radio(
        choices=[],
        label="Top 5 trending papers",
        visible=False,
        elem_id="paper-radio",
    )
    analyze_btn = gr.Button(
        "Analyze selected paper",
        variant="primary",
        visible=False,
        elem_id="analyze-btn",
    )

    output = gr.Markdown(value="", label="Report", min_height=400, elem_id="report-card")

    search_outputs = [status, progress_bar, papers_state, paper_radio, analyze_btn, output]
    search_btn.click(
        fn=do_search,
        inputs=[topic_input, field_preset],
        outputs=search_outputs,
    )
    topic_input.submit(
        fn=do_search,
        inputs=[topic_input, field_preset],
        outputs=search_outputs,
    )
    analyze_btn.click(
        fn=do_analyze,
        inputs=[paper_radio, papers_state, analyses_state, topic_input],
        outputs=[status, progress_bar, output, analyses_state],
    )


if __name__ == "__main__":
    demo.launch(theme=theme)
