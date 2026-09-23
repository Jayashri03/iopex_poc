import json
import re
from dataclasses import dataclass, field

from agent.llm import chat

SYSTEM_PROMPT_TEMPLATE = """You are a senior code reviewer agent for pull requests.

You work in a strict loop. On every turn you must respond with exactly one
JSON object and nothing else - no markdown fences, no prose outside the JSON.

Schema for every turn:
{{
  "thought": "your reasoning about what to do next",
  "action": "<one of: {tool_names}, final_answer>",
  "action_input": <object - tool arguments, or the final result if action is final_answer>
}}

Available tools:
{tool_descriptions}

When you have enough information, set "action" to "final_answer" and
"action_input" to:
{{
  "summary": "1-3 sentence overall assessment of the PR",
  "review_comments": [
    {{
      "file_path": "...",
      "line_hint": "e.g. a function name or approximate line",
      "severity": "high | medium | low",
      "category": "bug | merge_conflict | duplication | optimization | style | validation",
      "comment": "what's wrong and why it matters",
      "suggested_fix": "concrete suggested change"
    }}
  ],
  "merge_conflicts": [
    {{"file_path": "...", "detail": "what's unresolved, e.g. leftover <<<<<<< markers"}}
  ]
}}

Rules:
- Use tools to check for code duplication and to pull in context the diff
  hunk alone doesn't show, before writing your final answer.
- If a diff contains unresolved merge conflict markers (<<<<<<<, =======,
  >>>>>>>), always report it under merge_conflicts AND as a high severity
  review_comment - such a file will not run as-is.
- Only call final_answer once, as your last turn.
- You have at most {max_steps} turns before you must give a final_answer.
"""

PR_CONTEXT_TEMPLATE = """Review this pull request.

Title: {title}
Description: {description}
Author: {author}
Source branch -> Target branch: {source_branch} -> {target_branch}

Changed files and diffs:
{diffs}
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
        diffs = "\n\n".join(
            f"--- {f.file_path} ({f.change_type}) ---\n{f.diff_text}" for f in pr.files
        )
        user_prompt = PR_CONTEXT_TEMPLATE.format(
            title=pr.title,
            description=pr.description,
            author=pr.author,
            source_branch=pr.source_branch,
            target_branch=pr.target_branch,
            diffs=diffs,
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

            if action == "final_answer":
                if not isinstance(action_input, dict):
                    action_input = {}
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
