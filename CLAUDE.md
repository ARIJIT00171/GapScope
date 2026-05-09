# CLAUDE.md – Research Gap Mining Agent (Groq + LangGraph)

## Project Cnntext
Build a Gradio app that acts as a research assistant for users to search new and trending papers in the field, summarizing and identifying key research gaps to build new research.

## Example User Flow
1. User types “efficient fine‑tuning of LLMs”
2. Agent calls 'search_arxiv' (last 365 days, sort by submission date) for recent 10 papers
3. Agent calls 'fetch_citation_counts' for top 5 papers (Semantic Scholar)
4. Agent ranks by `citations_last_30d / age_days`
5. User selects top 2 (or agent auto‑selects)
6. For each: summarise → find gaps → generate ideas (one model call per paper)
7. Final report (markdown) appears in Gradio

**Zero cost**: uses Groq free tier for LLM inference.

## Tech Stack
- **UI**: Gradio (deployed on Hugging Face Spaces, SDK Gradio)
- **Agent orchestration**: LangGraph (state graph with nodes for search, rank, gap analysis, idea generation)
- **LLM**: Groq (model: "llama-3.3-70b-versatile")
- **APIs**: arXiv ('arxiv' library), Semantic Scholar (optional, for citation counts)
- **Caching**: Simple JSON cache to avoid repeated API calls
- **Environment**: python-dotenv for API keys

## Required Environment Variables
- `GROQ_API_KEY` – from console.groq.com (stored in .env file, do not commit)

## Project Structure
├── app.py # Gradio interface, orchestrates LangGraph
├── graph.py # LangGraph state & nodes (search, analyze, generate)
├── tools.py # Helper functions (arxiv search, citation fetch, caching)
├── prompts.py # Prompt templates for gap analysis & idea generation
├── cache.py # JSON cache management
├── requirements.txt # Dependencies
├── .env # Local keys (do not commit)
├── .gitignore #to include .env file and other files that we do not commit
└── README.md # Project description + deployment instructions

## Code Generation Rules
1. Use python to build the entire project.
2. Use **LangGraph** with a minimal state: 'topic', 'papers', 'current_paper_index','summary', 'results', 'gaps', 'ideas', 'final_report'.
3. Define nodes: 'search_arxiv', 'rank_trending', 'analyze_gap', 'generate_ideas', 'synthesize_report'.
4. Use Groq via LangChain’s `ChatGroq` (install `langchain-groq`). Temperature 0.3 for analysis, 0.7 for ideas.
5. Implement loading indicators in gradio during complex ingestions/loading.
6. Keep a contrasting user interface design in gradio for better user experience.
6. Implement retries with `tenacity` on API calls.
7. Implement safe falbback in case of too many requests and other failures.
8. Cache all paper metadata (arxiv results, citation counts) in a JSON file with TTL of 7 days.
9. The final output should contain: Paper Title, Summary, Key Results, Gaps Found, Novel Ideas
10. Error handling: if Semantic Scholar fails, try to debug. If it does not work then skip citation ranking and fall back to date sorting.
11. Keep each LLM call cheap – use `max_tokens=1600` for gap analysis, `max_tokens=1000` for ideas.
12. Include a progress bar in Gradio (using `gr.Progress`) when processing multiple papers.
13. Include a `demo` section in README with a screenshot.
14. Add a short analysis of model output quality (strengths/weaknesses).

## Deployment on Hugging Face Spaces
- Create a Space with **Gradio SDK**.
- Add `GROQ_API_KEY` to **Repository Secrets**.
- Commit all files except `.env` and `__pycache__`.
- Do not commit `cache.json` or any API keys.
- The Space will auto‑install from `requirements.txt`.