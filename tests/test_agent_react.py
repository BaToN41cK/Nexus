"""Tests for the ReAct agent module."""

import json
import unittest
from unittest.mock import MagicMock, patch

from nexus.core.agent_react import (
    ReactResult,
    ReactStep,
    ReActAgent,
    ToolRegistry,
    build_default_tools,
    parse_react_step,
)


class TestParseReactStep(unittest.TestCase):
    def test_parses_action(self):
        text = (
            "Thought: I should look this up online.\n"
            "Action: web_search\n"
            'Action Input: {"query": "weather Paris"}'
        )
        step = parse_react_step(text)
        self.assertEqual(step.thought, "I should look this up online.")
        self.assertEqual(step.action, "web_search")
        self.assertEqual(step.action_input, '{"query": "weather Paris"}')
        self.assertIsNone(step.final_answer)
        self.assertTrue(step.is_action)
        self.assertFalse(step.is_final)

    def test_parses_final_answer(self):
        text = (
            "Thought: I have enough info now.\n"
            "Final Answer: The weather is sunny."
        )
        step = parse_react_step(text)
        self.assertEqual(step.final_answer, "The weather is sunny.")
        self.assertTrue(step.is_final)
        self.assertFalse(step.is_action)

    def test_final_wins_over_action(self):
        text = (
            "Thought: done\n"
            "Action: web_search\n"
            "Action Input: q\n"
            "Final Answer: The answer is 42."
        )
        step = parse_react_step(text)
        self.assertTrue(step.is_final)
        self.assertEqual(step.final_answer, "The answer is 42.")

    def test_handles_no_markers(self):
        step = parse_react_step("Just some prose, no markers.")
        self.assertEqual(step.thought, "")
        self.assertIsNone(step.action)
        self.assertFalse(step.is_action)
        self.assertFalse(step.is_final)

    def test_case_insensitive(self):
        text = "thought: x\naction: tool\naction input: arg"
        step = parse_react_step(text)
        self.assertEqual(step.thought, "x")
        self.assertEqual(step.action, "tool")
        self.assertEqual(step.action_input, "arg")

    def test_action_takes_first_token(self):
        text = "Action: web_search extra junk"
        step = parse_react_step(text)
        self.assertEqual(step.action, "web_search")


class TestToolRegistry(unittest.TestCase):
    def test_register_and_call(self):
        reg = ToolRegistry()

        def echo(value):
            """Echo the input back."""
            return f"got: {value}"

        reg.register("echo", echo)
        self.assertTrue(reg.has("echo"))
        self.assertEqual(reg.call("echo", "hello"), "got: hello")

    def test_call_with_json_input(self):
        reg = ToolRegistry()
        reg.register("double", lambda v: str(int(v["n"]) * 2))
        self.assertEqual(reg.call("double", '{"n": 21}'), "42")

    def test_duplicate_registration_raises(self):
        reg = ToolRegistry()
        reg.register("x", lambda v: v)
        with self.assertRaises(ValueError):
            reg.register("x", lambda v: v)

    def test_unknown_tool_returns_error_message(self):
        reg = ToolRegistry()
        out = reg.call("missing", "x")
        self.assertIn("unknown tool", out)

    def test_tool_exception_is_caught(self):
        reg = ToolRegistry()
        reg.register("boom", lambda v: (_ for _ in ()).throw(RuntimeError("oops")))
        out = reg.call("boom", "x")
        self.assertIn("Error in tool", out)

    def test_describe_lists_tools(self):
        reg = ToolRegistry()
        reg.register("a", lambda v: v, "Does a.")
        reg.register("b", lambda v: v, "Does b.")
        desc = reg.describe()
        self.assertIn("- a:", desc)
        self.assertIn("- b:", desc)


class TestBuildDefaultTools(unittest.TestCase):
    def test_registers_web_search_and_web_fetch(self):
        reg = build_default_tools(web_searcher=None)
        self.assertTrue(reg.has("web_search"))
        self.assertTrue(reg.has("web_fetch"))

    def test_web_search_without_searcher_returns_error(self):
        reg = build_default_tools(web_searcher=None)
        out = reg.call("web_search", "weather")
        self.assertIn("not configured", out)

    def test_web_search_with_mocked_searcher(self):
        from nexus.core.web_search import SearchResult, WebSearcher, WebSearchConfig

        searcher = MagicMock(spec=WebSearcher)
        searcher.search.return_value = [
            SearchResult("Title A", "https://a", "Snippet A", "duckduckgo"),
            SearchResult("Title B", "https://b", "Snippet B", "duckduckgo"),
        ]
        reg = build_default_tools(web_searcher=searcher)
        out = reg.call("web_search", json.dumps({"query": "x", "max_results": 2}))
        self.assertIn("Title A", out)
        self.assertIn("https://a", out)
        searcher.search.assert_called_once()

    def test_web_fetch_rejects_empty_url(self):
        reg = build_default_tools()
        out = reg.call("web_fetch", "")
        self.assertIn("requires a non-empty URL", out)


class TestReActAgentLoop(unittest.TestCase):
    def _build_agent(self, scripted_responses):
        """Create a ReActAgent whose underlying NexusAgent returns scripted text."""
        underlying = MagicMock()
        underlying.generate_response.side_effect = [
            {"text": r, "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            for r in scripted_responses
        ]
        registry = ToolRegistry()
        registry.register(
            "echo",
            lambda v: f"ECHO: {v}",
            "Echo the input back.",
        )
        return ReActAgent(underlying, registry, max_iterations=5), underlying

    def test_final_answer_short_circuits(self):
        agent, _ = self._build_agent(["Final Answer: 42"])
        result = agent.run("What is the meaning of life?")
        self.assertEqual(result.final_answer, "42")
        self.assertEqual(result.iterations, 1)

    def test_executes_tool_then_answers(self):
        agent, _ = self._build_agent(
            [
                "Thought: need data\nAction: echo\nAction Input: hi",
                "Final Answer: got ECHO: hi",
            ]
        )
        result = agent.run("anything")
        self.assertEqual(result.final_answer, "got ECHO: hi")
        # Two LLM turns and one tool step in the transcript.
        llm_steps = [s for s in result.steps if s["type"] == "llm"]
        tool_steps = [s for s in result.steps if s["type"] == "tool"]
        self.assertEqual(len(llm_steps), 2)
        self.assertEqual(len(tool_steps), 1)
        self.assertEqual(tool_steps[0]["name"], "echo")
        self.assertEqual(tool_steps[0]["observation"], "ECHO: hi")

    def test_exhausts_iterations_and_uses_fallback(self):
        # The agent never emits a final answer or an action; the fallback
        # request is appended to the LLM call list.
        agent, underlying = self._build_agent(
            [
                "no markers at all",  # iter 1 -> nudge
                "still nothing",      # iter 2 -> nudge
                "Final Answer: forced",  # fallback iteration
            ]
        )
        result = agent.run("p")
        self.assertEqual(result.final_answer, "forced")
        self.assertEqual(underlying.generate_response.call_count, 3)
        self.assertEqual(result.iterations, 3)

    def test_unknown_tool_surfaces_error_in_observation(self):
        agent, _ = self._build_agent(
            [
                "Action: missing_tool\nAction Input: x",
                "Final Answer: handled",
            ]
        )
        result = agent.run("p")
        tool_steps = [s for s in result.steps if s["type"] == "tool"]
        self.assertEqual(len(tool_steps), 1)
        self.assertEqual(tool_steps[0]["name"], "missing_tool")
        self.assertIn("unknown tool", tool_steps[0]["observation"])
        self.assertEqual(result.final_answer, "handled")


if __name__ == "__main__":
    unittest.main()
