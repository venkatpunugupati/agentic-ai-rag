"""chunk.py — split docs/ into retrieval-ready chunks.

Strategy: recursive character splitting (paragraphs -> lines -> words),
target ~500 tokens per chunk with ~50 tokens of overlap.
Writes chunks_raw.json ([{text, source, index}]) and prints chunk
count + samples to eyeball boundary quality.
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUT_PATH = os.path.join(BASE_DIR, "chunks_raw.json")

TARGET_TOKENS = 500
OVERLAP_TOKENS = 50


def estimate_tokens(text):
    # ~4 chars per token. Approximate — good enough for chunking;
    # tiktoken would give the exact count.
    return max(1, len(text) // 4)


def split_recursive(text, target=TARGET_TOKENS, sep_idx=0):
    """Split on "\n\n", then "\n", then " " — coarsest separator first."""
    separators = ["\n\n", "\n", " "]
    #print(f"text is === {text}")

    text = text.strip()
    if not text or estimate_tokens(text) <= target or sep_idx >= len(separators):
        return [text] if text else []
    sep = separators[sep_idx]
    parts, out, buf = [p for p in text.split(sep) if p.strip()], [], ""
    for p in parts:
        candidate = (buf + sep + p) if buf else p
        if buf and estimate_tokens(candidate) > target:
            out.append(buf)
            buf = p
        else:
            buf = candidate
    if buf:
        out.append(buf)
    # Any piece still oversized gets split on the next-finer separator.
    final = []
    for piece in out:
        final.extend(split_recursive(piece, target, sep_idx + 1))
    return final


def with_overlap(pieces, overlap=OVERLAP_TOKENS):
    """Prepend the tail of the previous chunk so boundary ideas survive."""
    out = []
    for i, piece in enumerate(pieces):
        if i > 0:
            tail_words = out[-1].split()[-int(overlap * 0.75):]
            piece = " ".join(tail_words) + "\n\n" + piece
        out.append(piece)
    return out


def main():
    chunks = []
    files = sorted(f for f in os.listdir(DOCS_DIR)
                   if os.path.isfile(os.path.join(DOCS_DIR, f)))
    for fname in files:
        with open(os.path.join(DOCS_DIR, fname),
                  encoding="utf-8", errors="ignore") as f:
            text = f.read()
        for piece in with_overlap(split_recursive(text)):
            chunks.append({"text": piece, "source": fname, "index": len(chunks)})

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=1)

    print(f"files: {len(files)}  chunks: {len(chunks)} -> {OUT_PATH}")
    for c in chunks[:3]:
        print("=" * 60)
        print(f"[{c['source']} #{c['index']}] ~{estimate_tokens(c['text'])} tokens")
        print(c["text"][:600])


if __name__ == "__main__":
    main()
