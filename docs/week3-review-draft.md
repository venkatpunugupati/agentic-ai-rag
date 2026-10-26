# Week 3 Review — Frameworks: LangChain4j & Spring AI

*Theme: the same agent, three substrates. What the frameworks commoditized, what stayed mine.*

## Day-by-day

**Day 1 (Oct 12) — LangChain4j port.** New Maven project `~/Desktop/AI_Java/agent` (Java 27, Maven 3.10.0, langchain4j-bom 1.20.0 — 1.19.1 deliberately avoided over the wrong-branch incident). Three `@Tool` POJOs (hand-written recursive-descent calculator — no `eval` in the JDK), `Assistant` interface with `@SystemMessage`/`@MemoryId`/`@UserMessage`, `MessageWindowChatMemory` via `ChatMemoryProvider`. Verified: warmup 36, chained word_count→calculator (4 words → 12), same-JVM name recall, fresh-JVM forget. Theory set: annotations declare, the generated AiServices proxy runs the loop; no visible Thought text — reasoning goes latent.

**Day 2 (Oct 13) — `FileChatMemoryStore`.** One JSON file per memory id via `ChatMessageSerializer`/`Deserializer`, wired through the `ChatMemoryProvider`. Acceptance: fresh-JVM `user-1` recalled the name; `user-2` got "I don't have access to personal information" (routing by id, no leakage). Trace showed tool-request `AiMessage`s and `ToolExecutionResultMessage`s round-tripping through JSON. The `maxMessages(4)` probe: file pinned at 4, orphan eviction (evicting a tool-request dragged its result along), Q/A splitting, eventual name loss. Restored to 10. Distinction articulated: *eviction deletes; compaction distills.*

**Day 3 (Oct 14) — Spring AI port.** Standalone project `~/Desktop/AI_Java/agent_springAI` (Boot 4.1.0, Spring AI 2.0.1). Property rename caught live (`.options` segment gone in 2.0). First run 401'd — `OPENAI_API_KEY` not exported in the fresh VS Code terminal; the advisor chain was already correct. Acceptance family: chained question → 27; unattached current-time tool → honest refusal with zero `toolCalls` in the DEBUG trace; `max-total-tool-calls=1` probe → graceful final response, confirming the shipped 40/tool and 150/turn caps.

**Day 4 (Oct 15) — `GroundingVerificationAdvisor`.** Multi-turn CLI runner (one JVM, one request per arg, turn boundaries). Advisor at `ToolCallingAdvisor.DEFAULT_ORDER + 1` (−2147483348 + 1, verified via `javap`); correct method is `adviseCall`, not `adviseRequest`. Core seam found the hard way: a flag in `request.context()` does **not** survive tool-loop iterations (fresh context copy per iteration) — the once-per-turn bound uses a transcript scan for the `grounding-` marker instead. Synthetic `grounding-{id}` tool call verified: `ToolCallingAdvisor` detects it via `hasToolCalls()` and executes. All four acceptance tests passed: fault-injected stale temporal → fresh time; natural temporal → silent; non-temporal (15% of 240 → 36) → silent; exactly one marker per turn.

**Day 5 (Oct 16) — the compare.** Side-by-side chained question → 27 on all three, with three different tool-call shapes (Python 0 via the deterministic no-tool rule; LangChain4j 3 with a parallel-call hazard; Spring 2, clean sequential). Ledger written. Pending Week 2 compaction proof test **passed** — the volatile-fact drop-list is now trace-verified (see numbers).

## Numbers

| # | Measurement |
|---|---|
| `maxMessages(4)` probe (LC4j) | file pinned at 4; orphan eviction; Q/A split; name lost |
| Spring window | 20 (the "11-message mystery" — 11 ≤ 20, no eviction expected; resolved Oct 16) |
| Spring loop caps | 40/tool, 150/turn; limit=1 → graceful final response |
| Advisor order | `ToolCallingAdvisor.DEFAULT_ORDER` = −2147483348; verifier at +1 |
| Side-by-side prompt tokens | Python ~1,073 (3 calls) vs Spring ~672 (195→226→251) |
| Compaction proof (Oct 16) | summary held "Venkat", zero clock/date strings; fresh `get_current_time` on re-ask — drop-list verified |
| Python `compact_memory` (Week 2) | 691 → 489 tokens on compaction; name retained |

## Failure stories (with interview hooks)

1. **Dead provider (Day 2).** The new `FileChatMemoryStore` provider sat unwired — the assistant still used the heap-only one — and `args[0]` collided memory id with the question. Fix: wire the provider into the AiServices builder; id from `MEMORY_ID` env. *Hook: "I verify wiring with a negative control — user-2 must NOT know user-1's name."*
2. **Commented `.user(q)` (Day 4).** The runner loop referenced the question array instead of the current question. *Hook: haste bug, caught by reading the trace, not the code.*
3. **`adviseCall`, not `adviseRequest` (Day 4).** Wrong interface method name; compile error. *Hook: "I read the framework's interface, not just the tutorial."*
4. **The context-flag seam (Day 4).** Once-per-turn flag in `request.context()` silently didn't survive loop iterations. Fix: transcript marker scan. *Hook: "Framework internals beat my assumption — I verified with a trace, then designed around the real behavior."*
5. **The "date" false positive (Day 4).** Filler "say the word date" matched the temporal regex; advisor fabricated `getCurrentTime`. Known precision/recall tradeoff, disclosed not hidden. *Hook: "I can tell you where my verifier is imprecise and what it costs."*
6. **Upstream javadoc bug (Day 4).** `ToolCallingAdvisor`'s `advisorOrder` javadoc contradicts the ascending-sort implementation — verified against 2.0.1 source. *Hook: "I read framework source when docs and behavior disagree."*
7. **The 11-message window mystery (Oct 15–16).** Turn-6 prompt held 11 messages under an assumed `maxMessages(10)`. Resolution: the window had been changed to 20. *Hook: "I check my own config before blaming the framework."*
8. **The `phrase` TypeError (Day 5).** Model emitted `{"phrase": ...}`; `word_count()` wanted another kwarg — tool descriptions are `None`, so the model guesses arg names. Plus `TOOLS[name](**args)` unguarded: one bad call kills the run. Fix identified, not yet applied. *Hook: "Schemas aren't documentation — they're the contract the model reasons against."*
9. **The parallel-call hazard (Day 5).** LangChain4j fired `calculate("3")` in the same block as `countWords` — the dependency violation, live, self-corrected. *Hook: "This is what my plan-and-execute wrapper exists to prevent — sequential steps with injected results."*
10. **Duplicate `UserMessage` (Day 5, unverified).** The LC4j prompt carried the question twice — likely Main double-adding what the framework already adds. Open thread.

## The edge, in one paragraph

Both frameworks commoditized the loop, the window, the caps, and the tool schema plumbing. Neither ships grounding verification, rolling-summary compaction with a staleness policy, or plan-and-execute with bounded replanning — those are judgments, not machinery, and they ported: the verifier moved from raw Python to a Spring advisor in a day. Missing everywhere: token/dollar budget, write-tool approval, eval harness.

## Open threads

- `word_count` schema fix + guarded tool execution (story 8) — identified, not applied.
- LangChain4j duplicate `UserMessage` (story 10) — unverified.
- Contradictory facts still sampled, not versioned (Week 2 carryover).
- Optional: upstream Spring AI issue on the javadoc bug (public portfolio artifact).

## My framing (fill in)

- The one-line senior answer this week earned me:
- The Week 3 story I'd tell in an interview:
