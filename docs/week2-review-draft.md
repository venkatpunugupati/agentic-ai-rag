# Week 1–2 Review — draft skeleton (Friday Oct 9, 2026)

Fill the `[...]` gaps, then this is your portfolio + interview reference for Week 2.

## Week 1 — LLM fundamentals ✅ (Sep 30 → Oct 2)
- First LLM API call (Sep 30); learned what tokens are — the crypto-tokens prompt bug as a lesson in prompt ambiguity
- System prompts, few-shot prompting, embeddings
- `extract.py`: job-posting → JSON with exactly 5 keys (title, company, location, skills[], salary); system-prompt schema, temperature=0, JSON response mode, key validation, one bounded retry feeding the validation error back; both test postings ran end to end

## Week 2 — Agent architecture, raw ReAct from scratch ✅ closing today
- **Day 1 (Oct 5):** `agent.py` — Thought / Action / Action Input loop, tool observations, max 6 steps; tools: calculator, word_count, get_current_time (gpt-4o-mini, temp 0). Proof the loop is real: get_current_time returned a timestamp frozen training data couldn't know. First chained multi-tool run verified.
- **Day 2 (Oct 6):** Memory across runs — full message list → `memory.json` (load at startup, save at end, `--fresh` flag); prompt_tokens printed each run to watch growth.
- **Day 3 (Oct 7):** Compaction (rolling summary; `MAX_MSGS=12`) + guardrails v2. 484→1066 prompt-token growth motivated it. Summarizer keeps durable facts, drops volatile ones; `check_grounding` scans the trace for a get_current_time Action on temporal questions and appends one corrective observation for a bounded retry. Honest fallback on `stopped: max steps reached`.
- **Day 4 (Oct 8):** Plan-and-execute + bounded replanner. Planner emits `[tool]`-bracketed steps, deterministic validation against the tool registry (a hallucinated `[search]` was dropped live before any tokens were spent). Executor injects prior (step, answer) results; replanner returns CONTINUE / REVISE / DONE, failing open to CONTINUE, capped at `MAX_REPLANS=2`. AAPL forced-failure: honest refusal, no invented price.
- **Day 5 (Oct 9):** Capstone — full composition validate → plan → execute → verify → persist → compact. Three integration bugs found in code review and fixed yourself (tuple-leak into transcript, undefined `idx`, vacuous pre-execution grounding check); an indent bug that ran every step twice was fixed and trace-verified. Acceptance test 1: "9 words × hour 12 − 10" → **98**, replanner DONE early at 0/2 replans, tool-capable synthesis computed the answer itself. Summarizer now carries an explicit volatile-fact drop-list, closing the Day-3 staleness hole.

## Measured numbers (capture while fresh)
| Metric | Value |
|---|---|
| Prompt-token growth, uncompacted | 484 → 1066 |
| Compaction effect | 691 → 489 |
| Replanner noise bill, Oct 8 (2 redundant REVISEs) | 1,026 prompt tokens |
| Replanner bill, Oct 9 capstone | 622 prompt tokens (DONE at 0/2 replans) |
| Compaction trigger | MAX_MSGS = 12 |
| ReAct guard | max 6 steps |
| Replanner guard | MAX_REPLANS = 2, fail-open CONTINUE |
| `--fresh` purge run | 173 prompt tokens; 15% of 240 = 36.0 ✅ |
| Capstone acceptance | 9 words, hour 12, 9×12−10 = **98** ✅ |
| Triviality tax ("I like coffee") | 8 LLM calls for a 3-word statement → needs a router / fast path |

## Failure stories → interview answers (your scar tissue)
1. **Stale summarized time.** Compaction preserved "12:02 PM Oct 6" as a durable fact; agent served it Oct 7 with no tool call. Lesson: timeless vs time-sensitive facts need different memory treatment. Guardrail: `check_grounding` on temporal questions.
2. **Hallucinated `[search]`.** Planner twice invented a tool. Prompt tweak half-worked and cost tokens on every call; deterministic registry validation killed it for free. "Prompts suggest, code enforces."
3. **Indent bug.** Every step ran `run_agent` twice and recorded deflected answers, misleading the replanner. Fixed; trace-verified.
4. **Write-only memory.** After the Day 4 refactor, messages loaded and saved in `__main__` but were never threaded into execute_plan or synthesis. Diagnosed from the trace, not the guess.
5. **Tool-called ≠ answer-grounded.** The Biden answer passed the grounding check (tool was invoked) while the claim came from stale parametric memory. The check verifies invocation, not derivation. "The final answer is a claim; the tool-observed trace is evidence."
6. **Replanner noise.** 1,026 tokens on two redundant REVISE verdicts after 303.9 was already computed; the MAX_REPLANS=2 cap stopped the third. The prompt-rule fix was tried and reverted same evening (half-worked, taxed every verdict) — the cap plus fail-open CONTINUE is the retained behavior.

## Still open
- [ ] Compaction proof test on the Day-5 system (does the summary keep Venkat/likes-coffee/from-India and drop clock readings?) — `[result: ...]`
- Contradictory facts ("filter coffee" vs "indian food") get sampled, not versioned — acknowledged, unresolved
- Stretch not taken: plan-and-execute vs greedy ReAct token comparison on the same task

## What's next
Week 3 starts Monday: LangChain4j + Spring AI — rebuild the core in Java, on home turf.

---
*Skeleton prepared Oct 9, 2026 — facts from the week's chat traces and memory notes. You own the synthesis.*
