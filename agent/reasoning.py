import json
import re
from dataclasses import dataclass, field

from agent.context_builder import build_commit_context
from agent.llm import chat

SYSTEM_PROMPT_TEMPLATE = """You are a senior code reviewer agent for pull requests.

You work in a strict loop. On every turn you must respond with exactly one
JSON object and nothing else - no markdown fences, no prose outside the JSON.

Schema for every turn:
{{
  "thought": "your reasoning about what to do next",
  "action": "<one of: {tool_names}, final_answer>",
  "action_input": <object - tool arguments (or {{}} for no-argument tools), or the final result if action is final_answer>
}}

Available tools:
{tool_descriptions}

When you have enough information, set "action" to "final_answer" and
"action_input" to:
{{
  "summary": "1-3 sentence overall assessment of the PR, covering the cumulative effect of all its commits",
  "review_comments": [
    {{
      "file_path": "...",
      "line_hint": "e.g. a function name or approximate line",
      "severity": "high | medium | low",
      "category": "bug | merge_conflict | duplication | optimization | style | validation",
      "comment": "what's wrong and why it matters",
      "suggested_fix": "concrete suggested change",
      "introduced_in_commit": "the commit_sha that introduced (or failed to fix) this issue"
    }}
  ],
  "merge_conflicts": [
    {{"file_path": "...", "detail": "what's unresolved, e.g. leftover <<<<<<< markers", "introduced_in_commit": "commit_sha"}}
  ]
}}

Rules:
- You are given every commit in this PR, in order, with its own diff. Judge
  the PR by the CUMULATIVE state after all commits are applied, not any
  single commit in isolation. A bug introduced in an early commit is still
  a bug even if a later commit looks unrelated or only partially addresses
  it - trace whether it was actually fixed by the final commit.
- Use tools to check for code duplication and to pull in context the diffs
  don't show, before writing your final answer.
- If any commit's diff contains unresolved merge conflict markers (<<<<<<<,
  =======, >>>>>>>) that are not removed by a later commit, always report it
  under merge_conflicts AND as a high severity review_comment - such a file
  will not run as-is.
- Only call final_answer once, as your last turn.
- You have at most {max_steps} turns before you must give a final_answer.
"""

PR_CONTEXT_TEMPLATE = """Review this pull request. It has {commit_count} commit(s), applied in order.

Title: {title}
Description: {description}
Author: {author}
Source branch -> Target branch: {source_branch} -> {target_branch}

Commits (in order):
{commits}
"""


@dataclass
class ReasoningStep:
    step_number: int
    thought: str
    action: str
    action_input: dict
    observation: str


@dataclass
class AgentResult:
    summary: str
    review_comments: list[dict] = field(default_factory=list)
    merge_conflicts: list[dict] = field(default_factory=list)
    steps: list[ReasoningStep] = field(default_factory=list)


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            text = text[brace_start : brace_end + 1]
    return json.loads(text)


class ReviewAgent:
    def __init__(self, tools: dict, max_steps: int = 6):
        self.tools = tools
        self.max_steps = max_steps

    def run(self, pr) -> AgentResult:
        tool_descriptions = "\n".join(
            f"- {name}: {spec['description']}" for name, spec in self.tools.items()
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            tool_names=", ".join(self.tools.keys()),
            tool_descriptions=tool_descriptions,
            max_steps=self.max_steps,
        )
        commit_context = build_commit_context(pr)
        user_prompt = PR_CONTEXT_TEMPLATE.format(
            commit_count=commit_context.commit_count,
            title=pr.title,
            description=pr.description,
            author=pr.author,
            source_branch=pr.source_branch,
            target_branch=pr.target_branch,
            commits=commit_context.text,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        steps: list[ReasoningStep] = []

        for step_number in range(1, self.max_steps + 1):
            raw = chat(messages)

            try:
                parsed = _extract_json(raw)
            except (json.JSONDecodeError, ValueError):
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "Your last response was not valid JSON matching the schema. "
                        "Respond again with exactly one valid JSON object.",
                    }
                )
                steps.append(
                    ReasoningStep(
                        step_number=step_number,
                        thought="(unparseable model output)",
                        action="parse_error",
                        action_input={},
                        observation=raw[:500],
                    )
                )
                continue

            thought = parsed.get("thought", "")
            action = parsed.get("action", "")
            action_input = parsed.get("action_input", {})
            if not isinstance(action_input, dict):
                action_input = {}

            if action == "final_answer":
                steps.append(
                    ReasoningStep(
                        step_number=step_number,
                        thought=thought,
                        action="final_answer",
                        action_input=action_input,
                        observation="",
                    )
                )
                return AgentResult(
                    summary=action_input.get("summary", ""),
                    review_comments=action_input.get("review_comments", []),
                    merge_conflicts=action_input.get("merge_conflicts", []),
                    steps=steps,
                )

            tool = self.tools.get(action)
            if tool is None:
                observation = f"Unknown tool '{action}'. Available tools: {list(self.tools.keys())}"
            else:
                try:
                    observation = tool["func"](**action_input)
                except TypeError as exc:
                    observation = f"Bad arguments for tool '{action}': {exc}"

            steps.append(
                ReasoningStep(
                    step_number=step_number,
                    thought=thought,
                    action=action,
                    action_input=action_input,
                    observation=observation,
                )
            )

            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Observation: {observation}"})

        # Ran out of steps without an explicit final_answer - force one.
        messages.append(
            {
                "role": "user",
                "content": "You are out of turns. Respond now with only the final_answer JSON object.",
            }
        )
        raw = chat(messages)
        try:
            parsed = _extract_json(raw)
            action_input = parsed.get("action_input", parsed)
        except (json.JSONDecodeError, ValueError):
            action_input = {"summary": "Agent failed to produce a structured result in time."}

        steps.append(
            ReasoningStep(
                step_number=self.max_steps + 1,
                thought="Forced final answer after exhausting max_steps.",
                action="final_answer",
                action_input=action_input,
                observation="",
            )
        )
        return AgentResult(
            summary=action_input.get("summary", ""),
            review_comments=action_input.get("review_comments", []),
            merge_conflicts=action_input.get("merge_conflicts", []),
            steps=steps,
        )
