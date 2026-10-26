"""embed.py — embed chunks_raw.json with text-embedding-3-small.

Reads [{text, source, index}], batches through the OpenAI embedding API,
writes chunks.json ([{text, vector, source, index}]).
Sanity checks: every vector is 1536-dim; same-doc chunks cosine-closer
than cross-doc chunks.
"""

import os
import json
import math
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IN_PATH = os.path.join(BASE_DIR, "chunks_raw.json")
OUT_PATH = os.path.join(BASE_DIR, "chunks.json")

MODEL = "text-embedding-3-small"
EXPECTED_DIM = 1536
BATCH_SIZE = 100


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb)


def main():
    client = OpenAI()  # OPENAI_API_KEY from env, never in code
    with open(IN_PATH, encoding="utf-8") as f:
        chunks = json.load(f)

    texts = [c["text"] for c in chunks]
    vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = client.embeddings.create(model=MODEL, input=batch)
        # API returns one embedding per input, in order — sort defensively.
        vectors.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))

    assert all(len(v) == EXPECTED_DIM for v in vectors), "dim mismatch!"

    for c, v in zip(chunks, vectors):
        c["vector"] = v
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f)

    print(f"embedded {len(chunks)} chunks -> {OUT_PATH} (dim={EXPECTED_DIM})")

    # Smoke test: a same-doc pair should outscore a cross-doc pair.
    by_source = {}
    for c in chunks:
        by_source.setdefault(c["source"], []).append(c["vector"])
    sources = list(by_source)
    if len(sources) >= 2 and all(len(by_source[s]) >= 2 for s in sources[:2]):
        s1, s2 = sources[0], sources[1]
        same = cosine(by_source[s1][0], by_source[s1][1])
        cross = cosine(by_source[s1][0], by_source[s2][0])
        print(f"same-doc cosine:  {same:.3f}")
        print(f"cross-doc cosine: {cross:.3f}")
        print("PASS: same-doc closer" if same > cross
              else "WARN: cross-doc closer — inspect those chunks")


if __name__ == "__main__":
    main()
