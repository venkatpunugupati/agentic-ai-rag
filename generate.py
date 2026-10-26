"""generate.py — grounded generation over retrieve.py's top-k.

Pipeline: question -> retrieve top-3 -> refusal gate (code) -> prompt
(chunks as context, cite-or-refuse instructions) -> gpt-4o-mini, temp 0.
Usage: python rag/generate.py "your question"   (no arg -> test set)
"""

import os
import sys
import json
from openai import OpenAI

from retrieve import retrieve, CHUNKS_PATH, TOP_K

CHAT_MODEL = "gpt-4o-mini"
REFUSAL = "I don't have that in the documents."

# Refusal-gate calibration — from Day 2's live traces, not a textbook:
#   capital-of-USA (out of corpus): top1 0.113, top1-top3 gap 0.022 -> refuse
#   drop-list (weakest in-corpus winner): top1 0.269               -> answer
MIN_TOP_SCORE = 0.20
MIN_GAP = 0.05

TEST_QUESTIONS = [
    "what was the Spring AI javadoc bug?",
    "what is capital of USA?",
    "what does Spring AI commoditize and what stays mine?",
    "how does the grounding check work?",
]

SYSTEM = (
    "Answer only from the documents below. "
    "Cite each fact with the exact label shown above its chunk, "
    "e.g. [spring-ai-issue-7198-doc.md #11]. "
    "If the answer is not in the documents, say exactly: "
    f"'{REFUSAL}'"
)


def build_context(scored):
    blocks = []
    for score, c in scored:
        blocks.append(f"--- [{c['source']} #{c['index']}] ---\n{c['text']}")
    return "\n\n".join(blocks)


def answer(client, chunks, question):
    scored = retrieve(client, chunks, question, k=TOP_K)
    top_score = scored[0][0]
    gap = scored[0][0] - scored[-1][0]
    print(f"  top1={top_score:.3f}  gap(top1-top{TOP_K})={gap:.3f}")

    # Refusal gate: low AND flat -> the corpus has no answer. No model call.
    if top_score < MIN_TOP_SCORE and gap < MIN_GAP:
        print("  -> REFUSED in code (model not called)")
        return REFUSAL

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": f"DOCUMENTS:\n{build_context(scored)}\n\nQUESTION: {question}"},
        ],
    )
    return resp.choices[0].message.content


def main():
    client = OpenAI()
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    questions = [sys.argv[1]] if len(sys.argv) > 1 else TEST_QUESTIONS
    for q in questions:
        print("=" * 70)
        print(f"Q: {q}")
        print(answer(client, chunks, q))


if __name__ == "__main__":
    main()
