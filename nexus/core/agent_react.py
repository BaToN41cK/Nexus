"""
ReAct Agent Module

Implements the ReAct (Reasoning + Acting) pattern on top of :class:`NexusAgent`.

The LLM is instructed to alternate between:
  - ``Thought:``    internal reasoning about the next step
  - ``Action:``     name of a tool to invoke
  - ``Action Input:`` argument passed to the tool (JSON or plain text)
  - ``Observation:`` (filled by the system with the tool's result)
  - ``Final Answer:``  the final response shown to the user

The agent stops as soon as the LLM emits a ``Final Answer:`` line, or after
``max_iterations`` steps.  This module is provider-agnostic — the text is
parsed by :func:`parse_react_step` and tools are dispatched through
:class:`ToolRegistry`, so it works with any backend that produces text.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from nexus.core.agent import NexusAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

REACT_SYSTEM_PROMPT = """You are Nexus, an AI assistant with access to tools.

To answer the user's request, alternate between Thought, Action, Action Input and Observation steps. The system will run the tool and append an Observation for you.

Use EXACTLY this format (one section per line, no extra prose inside a section):

Thought: <your private reasoning about what to do next>
Action: <one of the available tool names>
Action Input: <a JSON object with the tool's arguments, or a plain string>

The system will reply with:
Observation: <tool result>

Repeat Thought/Action/Action Input/Observation as many times as needed. When you are ready to answer the user, write:

Final Answer: <the response to show to the user>

Rules:
- Only call tools that exist in the registry below.
- If a tool returns nothing useful, try a different query or another tool.
- Never invent tool results. Wait for the system Observation.
- Keep "Thought:" short — a single sentence is usually enough.
"""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# These patterns tolerate extra whitespace and case-insensitive prefixes.
_THINK_RE = re.compile(r"^\s*Thought\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_ACTION_RE = re.compile(r"^\s*Action\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_INPUT_RE = re.compile(r"^\s*Action Input\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE | re.DOTALL)
_FINAL_RE = re.compile(r"^\s*Final Answer\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE | re.DOTALL)


@dataclass
class ReactStep:
    """One parsed step produced by the LLM."""

    thought: str = ""
    action: Optional[str] = None
    action_input: str = ""
    final_answer: Optional[str] = None

    @property
    def is_final(self) -> bool:
        return self.final_answer is not None

    @property
    def is_action(self) -> bool:
        return self.action is not None and not self.is_final


def parse_react_step(text: str) -> ReactStep:
    """
    Parse a single LLM turn into a :class:`ReactStep`.

    The parser is intentionally forgiving: it looks for the first occurrence
    of each marker and ignores trailing prose. ``Final Answer`` wins over
    ``Action`` if both are present (the agent is done).
    """
    step = ReactStep()

    # Final answer (takes priority)
    final_match = _FINAL_RE.search(text)
    if final_match:
        step.final_answer = final_match.group(1).strip()
        return step

    thought_match = _THINK_RE.search(text)
    if thought_match:
        step.thought = thought_match.group(1).strip()

    action_match = _ACTION_RE.search(text)
    if action_match:
        step.action = action_match.group(1).strip().split()[0]  # first token only

    input_match = _INPUT_RE.search(text)
    if input_match:
        step.action_input = input_match.group(1).strip()

    return step


def _coerce_action_input(raw: str) -> Any:
    """
    Try to decode an ``Action Input`` value as JSON. Fall back to the raw
    string if the value is not valid JSON.
    """
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """
    Lightweight in-process tool registry.  Each tool is a callable that
    accepts a single positional argument (a parsed action input) and returns
    a string observation.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Callable[[Any], str]] = {}

    def register(self, name: str, fn: Callable[[Any], str], description: str = "") -> None:
        if name in self._tools:
            raise ValueError(f"Tool {name!r} is already registered")
        self._tools[name] = fn
        self._descriptions: Dict[str, str] = getattr(self, "_descriptions", {})
        self._descriptions[name] = description

    def has(self, name: str) -> bool:
        return name in self._tools

    def call(self, name: str, raw_input: str) -> str:
        if not self.has(name):
            return f"[Error: unknown tool {name!r}. Available: {', '.join(self._tools)}]"
        value = _coerce_action_input(raw_input)
        try:
            result = self._tools[name](value)
        except Exception as e:  # never let a tool crash the loop
            logger.exception("Tool %s raised", name)
            return f"[Error in tool {name!r}: {e}]"
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    def describe(self) -> str:
        lines = []
        for name, fn in self._tools.items():
            doc = (self._descriptions.get(name) or (fn.__doc__ or "")).strip().splitlines()[0]
            lines.append(f"- {name}: {doc}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default tools
# ---------------------------------------------------------------------------


def build_default_tools(web_searcher=None) -> ToolRegistry:
    """
    Build the default tool set:

    - ``web_search``: searches the web via the supplied :class:`WebSearcher`.
    - ``web_fetch``:   loads a URL (web page, PDF, YouTube, etc.).
    """
    registry = ToolRegistry()

    def web_search(value):
        """Search the web. Input: JSON {"query": "...", "max_results": N} or plain text query."""
        if isinstance(value, dict):
            query = str(value.get("query", "")).strip()
            max_results = int(value.get("max_results", 5))
        else:
            query = str(value).strip()
            max_results = 5
        if not query:
            return "[Error: web_search requires a non-empty query]"
        if web_searcher is None:
            return "[Error: web search is not configured]"
        results = web_searcher.search(query, max_results=max_results)
        if not results:
            return "No results found."
        lines = [f"[{i}] {r.title} -- {r.url}\n{r.snippet}" for i, r in enumerate(results, 1)]
        return "\n\n".join(lines)

    def web_fetch(value):
        """Fetch and read the content of a URL. Input: the URL string."""
        from nexus.core.content_loader import load

        url = str(value).strip() if not isinstance(value, dict) else str(value.get("url", "")).strip()
        if not url:
            return "[Error: web_fetch requires a non-empty URL]"
        # The content loader is local; we just need to truncate huge results.
        text = load(url)
        if not text or text.startswith("[") and ("Ошибка" in text or "Неизвестный" in text):
            return f"[Error fetching {url}: {text}]"
        # Truncate to keep prompts reasonable.
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... truncated, total {len(text)} chars ...]"
        return text

    registry.register("web_search", web_search, "Search the web and return the top results.")
    registry.register("web_fetch", web_fetch, "Fetch the textual content of a URL.")
    return registry


# ---------------------------------------------------------------------------
# ReAct agent
# ---------------------------------------------------------------------------


@dataclass
class ReactResult:
    """Final result of a ReAct run."""

    final_answer: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    duration_s: float = 0.0


class ReActAgent:
    """
    Reasoning + Acting agent that wraps a :class:`NexusAgent` and a
    :class:`ToolRegistry`.  Use :meth:`run` for a single, blocking run
    and :meth:`run_stream` to stream intermediate steps.
    """

    def __init__(
        self,
        agent: NexusAgent,
        tools: ToolRegistry,
        max_iterations: int = 6,
    ) -> None:
        self.agent = agent
        self.tools = tools
        self.max_iterations = max_iterations

    def _build_system_prompt(self) -> str:
        return f"{REACT_SYSTEM_PROMPT}\n\nAvailable tools:\n{self.tools.describe()}\n"

    # ---- public API ----

    def run(self, prompt: str, system_prompt: Optional[str] = None) -> ReactResult:
        """
        Run the ReAct loop until the LLM emits ``Final Answer:`` or the
        iteration budget is exhausted.
        """
        started = time.monotonic()
        transcript = self._build_initial_prompt(prompt, system_prompt)
        steps: List[Dict[str, Any]] = []
        final_answer = ""
        iterations = 0

        for i in range(self.max_iterations):
            iterations = i + 1
            result = self.agent.generate_response(transcript)
            text = result.get("text", "")
            steps.append({"type": "llm", "text": text, "tokens": result})

            step = parse_react_step(text)
            if step.is_final:
                final_answer = step.final_answer or ""
                break
            if step.is_action and step.action:
                observation = self.tools.call(step.action, step.action_input)
                steps.append(
                    {
                        "type": "tool",
                        "name": step.action,
                        "input": step.action_input,
                        "observation": observation,
                    }
                )
                transcript = self._append_step(transcript, step.thought, step.action, step.action_input, observation)
            else:
                # The LLM did not produce a usable action and did not finalize.
                # Force it to either answer or pick a tool.
                logger.debug("ReAct step %d produced no action/final; nudging", i + 1)
                transcript = self._append_nudge(transcript)
        else:
            logger.warning("ReAct agent exhausted %d iterations", self.max_iterations)

        if not final_answer:
            # Ask the LLM one more time for a direct answer using everything it learned.
            fallback = self.agent.generate_response(
                transcript
                + "\n\nYou have used all your tool calls. Provide the Final Answer now based on the observations above."
            )
            final_answer = parse_react_step(fallback.get("text", "")).final_answer or fallback.get("text", "").strip()

        return ReactResult(
            final_answer=final_answer,
            steps=steps,
            iterations=iterations,
            duration_s=time.monotonic() - started,
        )

    # ---- prompt construction ----

    @staticmethod
    def _build_initial_prompt(prompt: str, system_prompt: Optional[str]) -> str:
        parts: List[str] = []
        if system_prompt:
            parts.append(f"System note: {system_prompt}")
        parts.append(f"User question: {prompt}")
        parts.append("\nBegin with a Thought, then choose an Action.")
        return "\n".join(parts)

    @staticmethod
    def _append_step(transcript: str, thought: str, action: str, action_input: str, observation: str) -> str:
        return (
            transcript
            + f"\n\nThought: {thought}\n"
            + f"Action: {action}\n"
            + f"Action Input: {action_input}\n"
            + f"Observation: {observation}"
        )

    @staticmethod
    def _append_nudge(transcript: str) -> str:
        return (
            transcript
            + "\n\nReminder: reply with either 'Action: <tool>' followed by 'Action Input: ...' "
            + "or with 'Final Answer: <text>'."
        )
