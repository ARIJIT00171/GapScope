COMBINED_PROMPT = """You are a research assistant. Read the paper below and produce a structured analysis covering: a summary, key results, research gaps, and novel ideas to address those gaps.

Title: {title}

Abstract: {abstract}

Output exactly this markdown structure (do not add any preamble or closing remarks):

### Summary
- 4-6 bullet points covering the problem, method, and contribution

### Key Results
- 2-4 bullet points of the main empirical or theoretical results

### Gaps Found
1. **<short gap title>** - 2-3 sentences explaining the gap and why it matters
2. **<short gap title>** - 2-3 sentences
3. **<short gap title>** - 2-3 sentences

### Novel Ideas
1. **<idea title>**
   - Hypothesis: <one sentence>
   - Method sketch: <2-3 sentences on the proposed approach>
   - Expected outcome: <one sentence on what success would look like>
2. **<idea title>**
   - Hypothesis: <one sentence>
   - Method sketch: <2-3 sentences>
   - Expected outcome: <one sentence>

Rules:
- Be specific. Do not invent results that are not stated or implied by the abstract.
- Identify exactly 3 gaps and propose exactly 2 ideas.
- Gaps should be specific to this paper's claims and methodology, not generic ML criticism.
- Each idea should be concrete enough to start a small experiment, not a vague research program."""
