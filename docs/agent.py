import json,re,os
from datetime import datetime
from openai import OpenAI
client = OpenAI()
MODEL = "gpt-4o-mini"
MEMORY_FILE = "memory.json"
MAX_MSGS = 5

def load_memory():
   if not os.path.exists(MEMORY_FILE):
      return None
   try:
      with open(MEMORY_FILE, "r", encoding="utf-8") as f :
           return json.load(f)
   except (json.JSONDecodeError, OSError) as e :
      print(f"Warning: Failed to load memory file ({e}). Starting with fresh memory.")  
      return None
   
def validate_question(q):
   if not isinstance(q, str) or not q.strip():
        return False, "Question cannot be empty."
   return True, "Valid"
def check_grounding(question, run_messages):
   # Check if user prompt references temporal concepts
    temporal_pattern = r'\b(time|date|today|now)\b'
    if not re.search(temporal_pattern, question, re.IGNORECASE):
        return True, "Temporal grounding check skipped (not a temporal question)."
    # Check if get_current_time was called in any assistant turn during this run
    time_tool_called = False
    for msg in run_messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            # Matches 'Action: get_current_time' in the ReAct trace format
            if re.search(r"Action:\s*get_current_time\b", content):
                time_tool_called = True
                break

    if not time_tool_called:
        return False, "Flagged ungrounded: temporal question asked without calling 'get_current_time'."

    return True, "Grounded: time tool was executed."
def build_system_message():
    return {"role": "system", "content": SYSTEM.format(
        tools="\n".join(f"- {n}: {f.__doc__}" for n, f in TOOLS.items()))}  
def save_memory(messages):
    with open(MEMORY_FILE,'w',encoding="utf-8") as f :
       json.dump(messages, f, indent=2)
def compact_memory(messages, keep_recent=4):
    # Only compact if history exceeds system message + recent threshold + buffer
    if len(messages) <= 1 + keep_recent + 2:
        return messages

    system_msg = messages[0]
    old_turns = messages[1:-keep_recent]
    recent_turns = messages[-keep_recent:]

    # Synthesize old conversation turns into a bulleted summary
    summary_prompt = [
        {"role": "system", "content": "You are a concise conversation summarizer."},
        {
            "role": "user",
            "content": (
                "Summarize key facts, tool outputs, user preferences, and decisions from these turns "
                "in under 150 words.\n\n"
                "CRITICAL FILTERING RULES:\n"
                "- EXCLUDE volatile facts: drop specific times, clock readings, dates, and timestamp tool outputs "
                "(e.g., outputs from get_current_time).\n"
                "- INCLUDE durable facts only: keep user preferences, calculated numerical results, "
                "entities, established decisions, and key tool findings that remain permanently true.\n\n"
                f"Turns to summarize:\n{json.dumps(old_turns)}"
            ),
        },
    ]

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=summary_prompt
    )
    summary_text = response.choices[0].message.content

    summary_msg = {
        "role": "system",
        "content": f"[Summary of prior steps]:\n{summary_text}"
    }

    return [system_msg, summary_msg] + recent_turns
  
def calculator(expression: str) -> str:
    if not re.fullmatch(r"[\d\s+\-*/%().]+", expression):
     return "Error: invalid characters in expression"
    try:
     return str(eval(expression ,{"__builtins__":{}},{}))
    except Exception as e:
     return f"Error: {e}"

def word_count(text: str) -> str:
    return str(len(text.split()))
def get_current_time() -> str:
   """Returns the current local date and time. Call this for any question about the current time or date. Takes no arguments, pass {}."""
   return  datetime.now().strftime("%Y-%m-%d %H:%M:%S")

TOOLS = {"calculator": calculator, "word_count": word_count,"get_current_time": get_current_time}
tools_str = "\n".join(f"- {n}: {f.__doc__}" for n, f in TOOLS.items())
SYSTEM = """You solve problems step by step using tools.
Tools:
{tools}

Use EXACTLY this format:
Thought: <reasoning about what to do next>
Action: <tool name>
Action Input: <JSON args, e.g. {{"expression": "2+2"}}>
(You will receive an Observation. Then continue.)
Thought: <reasoning>
Final Answer: <answer to the user>

Rules: start every turn with Thought. One action per turn.
If the user's message needs no tools (a greeting, a statement, or something
you already know), skip the tools: output Thought and then Final Answer directly.
When you have enough information, output Final Answer and stop."""

def make_plan(question: str) -> list[dict]:
    planner_system_prompt = (
        "You are a strategic planning agent. Your task is to break down the user's "
        "question into a minimal, logical, step-by-step plan using available tools "
        f"Available Tools:\n{tools_str}\n\n"
        "Output ONLY a numbered list of steps, one per line, with no extra intro or outro text.\n"
        "Example:\n"
        "1. [get_current_time] Get the current year.\n"
        "2. [calculator] Compute 15% of the year from step 1.\n"
        "3. [synthesize] State the final answer."
    )

    messages = [
        {"role": "system", "content": planner_system_prompt},
        {
            "role": "user",
            "content": f"Create a step-by-step plan to answer: {question}",
        },
    ]

    response = client.chat.completions.create(
        model=MODEL, temperature=0, messages=messages
    )

    plan_text = response.choices[0].message.content.strip()

    plan = []
    for line in plan_text.splitlines():
        line = line.strip()
        if not line:
            continue
        step_text = re.sub(r"^(\d+[\.\)]|\-|\*)\s*", "", line).strip()
        if step_text:
            plan.append({"step": step_text, "status": "pending"})
    # Validate: every step's [bracket] must name a real tool or [synthesize]
    valid_plan = []
    for item in plan:
        m = re.search(r"\[(\w+)\]", item["step"])
        name = m.group(1) if m else None
        if name in TOOLS or name == "synthesize":
           valid_plan.append(item)
        else:
            print(f"[Plan validation] Dropping step with unknown tool: {item['step']}")
    plan = valid_plan

    print("\n=== Initial Plan Generated ===")
    for idx, item in enumerate(plan, 1):
        print(f"  [{idx}] [{item['status'].upper()}] {item['step']}")
    print("==============================\n")
    return plan

def execute_plan(question,plan,history):
    """Executes a plan step-by-step with dynamic replanning after each step.

    Args:
        question: The original user question.
        plan: Initial plan containing step dictionaries [{"step": "...", "status": "pending"}, ...].

    Returns:
        tuple: (results, final_answer)
            results: List of (step_text, answer) tuples.
            final_answer: The final synthesized answer or the answer from the last step.
    """
    results = [] 
    current_plan = list(plan)  # Copy initial plan
    replan_count = 0
    step_num = 0
    while current_plan:
        # Find next pending step
        current_step_item = next((s for s in current_plan if s.get("status") == "pending"), None)
        if not current_step_item:
            break  # All steps executed
        step_num += 1
        step_text = current_step_item["step"]

        # 1. Render step input with prior results context
        if results:
            prior_context = "Previous step results:\n" + "\n".join(
                f"- {s}: {a}" for s, a in results
            )
            step_input = f"{prior_context}\n\nTask: {step_text}\nUse the completed results above; do not redo completed steps."
        else:
            step_input = step_text

        step_messages = history[:-1] + [
            {"role": "user", "content": step_input},
        ]

        # 2. Run agent for the step
        answer = run_agent(step_messages)

        # 3. Post-run grounding verification with one bounded retry
        grounded, ground_reason = check_grounding(step_text, step_messages)
        if not grounded:
            print(f"  [Grounding Violation in Step {step_num}]: {ground_reason} — retrying.")
            step_messages.append({
                "role": "user",
                "content": (
                "Observation: Time or temporal questions require calling get_current_time. "
                "Call get_current_time now, then provide the final step answer."
            ),
        })
            answer = run_agent(step_messages)
            grounded, ground_reason = check_grounding(step_text, step_messages)
            if not grounded:
                print(f"  [Warning - Step {step_num} Still Ungrounded]: {ground_reason}")

        # 3. Record result & mark step as done
        results.append((step_text, answer))
        current_step_item["status"] = "done"

        print(f"[EXECUTED STEP]: {step_text}\n[ANSWER]: {answer}\n")

        # 4. Extract remaining pending steps for replanning evaluation
        remaining_steps = [s for s in current_plan if s.get("status") == "pending"]

        # If no steps remain, break and proceed to final synthesis
        if not remaining_steps:
            break

        # 5. Invoke Replanner
        verdict, new_remaining_steps = replan(question, results, remaining_steps)
        print(f"[REPLAN VERDICT]: {verdict} (Replans so far: {replan_count}/{MAX_REPLANS})")

        if verdict == "DONE":
            print("[REPLAN]: Replanner marked task as DONE early.")
            break

        elif verdict == "REVISE" and replan_count < MAX_REPLANS:
            replan_count += 1
            print(f"[REPLAN]: Plan revised. Swapping in {len(new_remaining_steps)} new remaining step(s).")
            # Keep completed steps, drop old pending steps, append new revised pending steps
            completed_steps = [s for s in current_plan if s.get("status") == "done"]
            current_plan = completed_steps + new_remaining_steps

            print("\n=== Updated Plan ===")
            for idx, item in enumerate(current_plan, 1):
                print(f"  [{idx}] [{item['status'].upper()}] {item['step']}")
            print("====================\n")

        else:
            # CONTINUE or cap hit -> proceed as-is
            if verdict == "REVISE" and replan_count >= MAX_REPLANS:
                print("[REPLAN]: Revision requested but MAX_REPLANS cap reached. Proceeding with existing plan.")

    # 6. Final Answer Synthesis
    if results:
        # Generate a final consolidated response based on all step outputs
        synthesis_prompt = history[:-1] + [
            {
                "role": "user",
                "content": (
                    f"Original Question: {question}\n\n"
                    f"Execution History:\n" +
                    "\n".join(f"- {s}: {a}" for s, a in results) +
                    "\n\nProvide the final, clear, and direct answer to the user's question based on the above results."
                    "Respond with exactly:"
                    "Thought: <brief reasoning>"
                    "Final Answer: <the answer>"
                )
            }
        ]
        final_answer = run_agent(synthesis_prompt)
    else:
        final_answer = "No execution steps completed."

    return results, final_answer

MAX_REPLANS = 2
def replan(question, results, remaining_steps):
    """Evaluates progress and decides whether to CONTINUE, REVISE, or declare DONE.

    Args:
        question: Original user query.
        results: List of completed (step_text, answer) tuples.
        remaining_steps: List of pending step dicts (e.g. [{"step": "..."}, ...]).

    Returns:
        tuple: (verdict, new_remaining_steps)
            verdict: "CONTINUE", "REVISE", or "DONE"
            new_remaining_steps: Updated list of remaining step dicts
    """
    # 1. Format inputs for prompt context
    completed_str = "\n".join(
        f"- Step: {s}\n  Result: {a}" for s, a in results
    ) if results else "None"

    remaining_str = "\n".join(
        f"- {item['step'] if isinstance(item, dict) else item.step}"
        for item in remaining_steps
    ) if remaining_steps else "None"

    replanning_prompt = (
        "You are a dynamic replanning agent monitoring execution progress.\n\n"
        f"Original Question: {question}\n\n"
        f"Completed Steps and Results:\n{completed_str}\n\n"
        f"Remaining Planned Steps:\n{remaining_str}\n\n"
        "Evaluate if the completed results are sufficient to answer the original question, "
        "if the remaining plan is still valid, or if a revised plan is needed.\n\n"
        "You must output using EXACTLY this contract:\n"
        "VERDICT: CONTINUE | REVISE | DONE\n"
        "REVISED PLAN:\n"
        "1. [tool_name] First step\n"
        "2. [tool_name] Second step\n\n"
        "Rules:\n"
        "- VERDICT must be one of: CONTINUE, REVISE, or DONE.\n"
        "- ONLY include 'REVISED PLAN:' if VERDICT is REVISE.\n"
        "- If REVISE, provide remaining steps using the standard [tool_name] format."
    )

    messages = [
        {"role": "system", "content": "You are a precise, failure-resistant replanning agent."},
        {"role": "user", "content": replanning_prompt}
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=messages
        )
        output = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Warning: Replanner LLM call failed ({e}). Defaulting to CONTINUE.")
        return "CONTINUE", remaining_steps
    print(f"  [replan tokens] prompt={response.usage.prompt_tokens}")

    # 2. Defensive Parsing — Fail-open to CONTINUE
    verdict_match = re.search(r"VERDICT:\s*(CONTINUE|REVISE|DONE)", output, re.IGNORECASE)
    if not verdict_match:
        print("Warning: Unparseable verdict from replanner. Defaulting to CONTINUE.")
        return "CONTINUE", remaining_steps

    verdict = verdict_match.group(1).upper()
    
    # 3. Handle REVISE Verdict
    if verdict == "REVISE":
        parsed_revised_steps = []
        
        # Isolate revised plan section if present
        plan_part = output.split("REVISED PLAN:")[-1] if "REVISED PLAN:" in output else output
        
        for line in plan_part.splitlines():
            line = line.strip()
            if not line or line.upper().startswith("VERDICT:"):
                continue
            
            # Use make_plan strip-numbering logic
            step_text = re.sub(r"^(\d+[\.\)]|\-|\*)\s*", "", line).strip()
            
            # Validate [tool] bracket: must name a real tool or [synthesize]
            m = re.search(r"^\[(\w+)\]", step_text)
            name = m.group(1) if m else None
            if step_text and (name in TOOLS or name == "synthesize"):
                parsed_revised_steps.append({"step": step_text, "status": "pending"})

        # Fail-safe: If revision extraction failed or produced no valid steps, keep remaining steps
        if not parsed_revised_steps:
            print("Warning: REVISE specified but failed to parse valid bracketed steps. Defaulting to CONTINUE.")
            return "CONTINUE", remaining_steps

        return "REVISE", parsed_revised_steps

    return verdict, remaining_steps


def run_agent(messages, max_steps=6):
    
    for step in range(max_steps):
        resp = client.chat.completions.create(
            model=MODEL, temperature=0,messages=messages)
        text = resp.choices[0].message.content
        print(f"--- step {step} ---\n{text}\n")
        messages.append({"role": "assistant", "content": text})
        print(f"  [tokens]-- In run_agent prompt={resp.usage.prompt_tokens}")

        if "Final Answer:" in text:
            return text.split("Final Answer:")[1].strip()
        action_match = re.search(r"Action:\s*(\w+)", text)
        input_match = re.search(r"Action Input:\s*(\{.*\})", text, re.DOTALL)
        if not action_match or not input_match:
         observation = ("Error: could not parse Action. Use exactly:\n"
                    "Action: <tool name>\n"
                    'Action Input: {"arg": "value"}')
        else:
            try:
                args = json.loads(input_match.group(1))
            except json.JSONDecodeError as e:
                observation = f"Error: invalid JSON in Action Input: {e}"
            else:
                name = action_match.group(1)
                if name not in TOOLS:
                    observation = f"Error: unknown tool '{name}'. Available: {', '.join(TOOLS)}"
                else:
                    observation = TOOLS[name](**args)
            messages.append({"role": "user", "content": f"Observation: {observation}"})

    return "stopped: max steps reached"
    

if __name__ == "__main__":
    import sys
    fresh = "--fresh" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    question = args[0] if args else "What is 15% of 240?"

    messages = None if fresh else load_memory()
   
    if messages is None:
        messages = [build_system_message()]
    if len(messages) > MAX_MSGS: 
       messages = compact_memory(messages)   

    # 1. Validate Input
    valid, reason = validate_question(question)
    if not valid:
        print(f"Invalid input: {reason}")
        sys.exit(1)   
    messages.append({"role": "user", "content": question})
    plan = make_plan(question)
    results, final_answer = execute_plan(question, plan, messages)
    print(f"\nFinal Execution Results:\n{results}")
    print(f"\nFinal Answer:\n{final_answer}")
    if "stopped" not in final_answer.lower() :
       messages.append({"role": "assistant", "content": final_answer})
    save_memory(messages)