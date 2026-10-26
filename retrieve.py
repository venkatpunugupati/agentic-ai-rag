"""retrieve.py — embed a question, cosine-rank all chunks, print top-k.

Reads chunks.json ([{text, vector, source, index}]).
No generation model involved: retrieval, judged on its own.
Usage: python rag/retrieve.py "your question"   (no arg -> test set)
"""

import os
import sys
import json
import math
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNKS_PATH = os.path.join(BASE_DIR, "chunks.json")

MODEL = "text-embedding-3-small"  # must match embed.py — same vector space
TOP_K = 5

TEST_QUESTIONS = [
    "what was the Spring AI javadoc bug?",
    "what does Spring AI commoditize and what stays mine?",
    "what is the volatile-fact drop-list?",
    "how does the grounding check work?",
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


def retrieve(client, chunks, question, k=TOP_K):
    resp = client.embeddings.create(model=MODEL, input=[question])
    qvec = resp.data[0].embedding
    scored = [(cosine(qvec, c["vector"]), c) for c in chunks]
    scored.sort(key=lambda t: t[0], reverse=True)
    #for score, c in scored[:21]:
     #print(f"{score:.3f}  [{c['source']} #{c['index']}]")

    return scored[:k]


def main():
    client = OpenAI()
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)

    questions = [sys.argv[1]] if len(sys.argv) > 1 else TEST_QUESTIONS
    for q in questions:
        print("=" * 70)
        print(f"Q: {q}")
        for score, c in retrieve(client, chunks, q):
            snippet = c["text"][:200].replace("\n", " ")
            print(f"  {score:.3f}  [{c['source']} #{c['index']}]  {snippet}...")


if __name__ == "__main__":
    main()
