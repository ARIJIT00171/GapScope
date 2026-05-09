import os

from dotenv import load_dotenv
import gradio as gr

load_dotenv()

from graph import compiled_graph

FIELD_PRESETS: dict[str, str] = {
    "AI / ML (general)": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:cs.CV OR cat:stat.ML",
    "NLP only": "cat:cs.CL OR cat:cs.AI OR cat:cs.LG",
    "Computer Vision only": "cat:cs.CV OR cat:cs.AI OR cat:cs.LG",
    "Robotics": "cat:cs.RO OR cat:cs.AI OR cat:cs.LG",
    "Reinforcement Learning": "cat:cs.LG OR cat:cs.AI OR cat:cs.MA",
    "All CS": "cat:cs.*",
    "All categories (no filter)": "",
}
DEFAULT_PRESET = "AI / ML (general)"


def run_analysis(topic: str, field_preset: str):
    if not topic or not topic.strip():
        yield "Please enter a research topic.", 0, ""
        return
    if not os.environ.get("GROQ_API_KEY") or os.environ["GROQ_API_KEY"].startswith("your_"):
        yield "**Error:** `GROQ_API_KEY` is not set. Add it to `.env` and restart.", 0, ""
        return

    topic = topic.strip()

    category_query = FIELD_PRESETS.get(field_preset, FIELD_PRESETS[DEFAULT_PRESET])

    initial_state = {
        "topic": topic,
        "category_query": category_query,
        "papers": [],
        "top_papers": [],
        "current_paper_index": 0,
        "paper_analysis": "",
        "results": [],
        "final_report": "",
        "error": "",
    }

    try:
        yield "**Searching arXiv for recent papers...**", 5, ""

        final_state = None
        last_idx = -1
        for event in compiled_graph.stream(initial_state, stream_mode="values"):
            final_state = event
            n_results = len(event.get("results", []))
            n_top = len(event.get("top_papers", []))

            if event.get("error"):
                yield f"**arXiv error: {event['error']}**", 100, ""
                continue

            if not event.get("papers"):
                yield "**Searching arXiv for recent papers...**", 10, ""
            elif not event.get("top_papers"):
                msg = f"**Ranking {len(event['papers'])} papers by trending score...**"
                yield msg, 25, ""
            elif n_results != last_idx:
                last_idx = n_results
                if n_results < n_top:
                    msg = f"**Analyzing paper {n_results + 1} of {n_top}...** (summary, gaps, and ideas in one pass)"
                    pct = int(30 + 60 * (n_results / max(n_top, 1)))
                    yield msg, pct, ""
                else:
                    yield "**Synthesizing final report...**", 95, ""

        if final_state and final_state.get("final_report"):
            yield "**Done.**", 100, final_state["final_report"]
        else:
            yield "**No results.**", 100, "No results produced. Try a different topic."
    except Exception as e:
        yield f"**Error:** {type(e).__name__}", 100, f"**Error:** {type(e).__name__}: {e}"


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
    background: linear-gradient(90deg, #4f46e5 0%, #10b981 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin: 0;
}
#gs-tagline { text-align: center; color: #64748b; margin: 4px 0 18px; font-size: 1rem; }
#status-line { min-height: 1.5em; padding: 4px 0; color: #475569; font-size: 0.95rem; }
#report-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 24px 28px; margin-top: 12px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}
#report-card h1 { font-size: 1.8rem; border-bottom: 2px solid #e0e7ff; padding-bottom: 6px; }
#report-card h2 { font-size: 1.3rem; color: #4338ca; margin-top: 1.4em; }
#report-card h3 { font-size: 1.05rem; color: #0f766e; margin-top: 1em; }
#report-card hr { border: none; border-top: 1px dashed #cbd5e1; margin: 1.6em 0; }
#report-card a { color: #4f46e5; text-decoration: none; }
#report-card a:hover { text-decoration: underline; }
#mine-btn { min-height: 44px; }
"""

with gr.Blocks(title="GapScope", css=CUSTOM_CSS) as demo:
    with gr.Column(elem_id="gs-header"):
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
        submit = gr.Button("Mine gaps", variant="primary", scale=1, elem_id="mine-btn")

    status = gr.Markdown(value="", elem_id="status-line")
    progress_bar = gr.Slider(
        minimum=0,
        maximum=100,
        value=0,
        step=1,
        label="Progress (%)",
        interactive=False,
    )
    output = gr.Markdown(value="", label="Report", min_height=400, elem_id="report-card")

    submit.click(
        fn=run_analysis,
        inputs=[topic_input, field_preset],
        outputs=[status, progress_bar, output],
    )
    topic_input.submit(
        fn=run_analysis,
        inputs=[topic_input, field_preset],
        outputs=[status, progress_bar, output],
    )


if __name__ == "__main__":
    demo.launch(theme=theme)
