
# Applied RAG + Agentic RAG


## The pipeline

Corpus: 4 documents the author knows cold → 21 chunks. The first pass produced 79 chunks, 58 of them PDF binary garbage —
swapped the PDF for .md.

- `chunk.py`: recursive character splitter — paragraphs → lines → words —
  ~500 tokens per chunk, ~50 overlap. A widely adopted production
  baseline, balancing retrieval precision against contextual completeness.
- `embed.py`: text-embedding-3-small, 1536-dim vectors into `chunks.json`.
- `retrieve.py`: same embedding model for queries (non-negotiable — a
  different model lives in a different vector space), brute-force cosine,
  top-k=3, no generation in the loop.
- `generate.py`: chunks stuffed into the prompt as context, gpt-4o-mini,
  temperature 0, citations as exact chunk labels.

## The refusal gate

Code-side, before any model call: refuse when top1 < 0.20 AND
gap(top1−top3) < 0.05, with the verbatim refusal "I don't have that in
the documents." Calibrated from the author's own traces, not a textbook:
in-corpus winners scored 0.269–0.508, the out-of-corpus signature sat at
0.113 flat. "≥0.75 similarity" is folklore — the best verified match
scored 0.508. Thresholds are a property of the model+corpus pair.

## Measured failure modes 

- **Chunk-size sweep:** 250/25 crisper for thematic/diffuse questions;
  1000/100 caused the only dilution false refusal (commoditize top1
  0.399, gate passed, model refused anyway) and stuffed ~3,000 context
  tokens per query for the worst results. No single winner: factual
  questions tolerate any size; thematic and diffuse need small chunks.
- **k sweep on the 500/50 baseline:** k=3 is the knee. k=1 caused an
  evidence-starvation false refusal and amputated the diffuse answer;
  k=5 reproduced k=3 identically at ~2,500 vs ~1,500 tokens per query —
  zero quality return.
- **Citations:** the model cites rank, not provenance — logged 3×. A
  generation-discipline failure no retrieval knob fixes.

## Agentic RAG (`agent_rag.py`)

A copy of the agent (original left frozen) with `search_docs`
added to the TOOLS registry. Two facts about this codebase: the
docstring IS the tool description (both prompts render `f.__doc__`), so
the routing contract lives in the docstring; and no function calls
`search_docs` directly — the single dispatch site is
`TOOLS[name](**args)`, so the model is effectively the caller.

Conditional retrieval, measured: the doc question paid ~1,400 tokens of
chunks (prompt 325→1,708); the time question paid ~50 (632→682→703)
with zero retrieval.

Three named failures from the five-question acceptance set:

- **Behavioral refusal leaking:** the agent judged the corpus empty and
  cited nothing, then answered from training weights anyway — where Day
  3's code gate had been airtight. Judgment correct, discipline not.
  The prompt asks; the code guarantees.
- **Entity collision:** two artifacts share one name in the corpus
  (Python `check_grounding` vs Spring's `GroundingVerificationAdvisor`).
  Retrieval split the vote; generation fused them into a hybrid with
  zero citations. Dilution buries, starvation withholds, collision
  merges two answers into a third thing that is neither.
- **Synthesis-layer drop:** the step layer earned citations and refusal
  caveats; the final synthesis pass stripped both, because its prompt
  never mentions citations or refusals.

## Run it

python -m venv .venv
source .venv/bin/activate
pip install openai
export OPENAI_API_KEY="..."
python chunk.py && python embed.py
python retrieve.py
python generate.py
python agent_rag.py "what was the Spring AI javadoc bug?"

