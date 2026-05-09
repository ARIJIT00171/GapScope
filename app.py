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

with gr.Blocks(title="GapScope") as demo:
    gr.Markdown("# GapScope")
    gr.Markdown(
        "Enter a research topic. The agent searches recent arXiv papers (last 365 days) "
        "via OpenAlex (with arXiv as fallback), ranks by trending score, then identifies "
        "research gaps and proposes novel ideas for the top 2 papers."
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
        submit = gr.Button("Mine gaps", variant="primary", scale=1)

    status = gr.Markdown(value="", elem_id="status-line")
    progress_bar = gr.Slider(
        minimum=0,
        maximum=100,
        value=0,
        step=1,
        label="Progress (%)",
        interactive=False,
    )
    output = gr.Markdown(value="", label="Report", min_height=400)

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
