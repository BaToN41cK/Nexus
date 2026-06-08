"""Unit tests for the :mod:`nexus.core.agent` module.

These tests focus on the public API of :class:`NexusAgent` and verify that
the internal helper methods correctly build the message payloads and that the
agent delegates to the underlying provider.  The real provider implementations
are replaced with :class:`unittest.mock.MagicMock` objects so that no network
calls are performed.
"""

import unittest
from unittest.mock import MagicMock, patch

from nexus.core.agent import NexusAgent


class TestNexusAgent(unittest.TestCase):
    def setUp(self):
        # Patch ``create_provider`` to return a mock provider instance.
        self.provider_mock = MagicMock()
        self.provider_mock.generate.return_value = {
            "text": "mock response",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        }
        self.provider_mock.generate_stream.return_value = iter(["tok1", "tok2"])

        patcher = patch("nexus.core.agent.create_provider", return_value=self.provider_mock)
        self.addCleanup(patcher.stop)
        self.mock_create_provider = patcher.start()

        # Initialise the agent with dummy credentials – the provider is mocked
        # so the values are irrelevant.
        self.agent = NexusAgent(
            api_key="dummy",
            model="test-model",
            provider="groq",
        )

    def test_build_messages_without_system_or_history(self):
        msgs = self.agent._build_messages(prompt="hello")
        self.assertEqual(msgs, [{"role": "user", "content": "hello"}])

    def test_build_messages_with_system_and_history(self):
        history = [{"role": "assistant", "content": "prev"}]
        msgs = self.agent._build_messages(
            prompt="question",
            system_prompt="system",
            history=history,
        )
        expected = [
            {"role": "system", "content": "system"},
            {"role": "assistant", "content": "prev"},
            {"role": "user", "content": "question"},
        ]
        self.assertEqual(msgs, expected)

    def test_build_messages_with_system_only(self):
        msgs = self.agent._build_messages(prompt="hi", system_prompt="sys")
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")

    def test_build_messages_with_history_only(self):
        history = [{"role": "assistant", "content": "prev"}]
        msgs = self.agent._build_messages(prompt="hi", history=history)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "assistant")
        self.assertEqual(msgs[1]["role"], "user")

    def test_generate_response_delegates_to_provider(self):
        result = self.agent.generate_response(prompt="test")
        # Ensure the provider's ``generate`` method was called with the
        # correctly built message list and ``stream=False``.
        self.provider_mock.generate.assert_called_once()
        args, kwargs = self.provider_mock.generate.call_args
        self.assertIsInstance(args[0], list)  # messages list
        self.assertFalse(kwargs.get("stream", True))
        self.assertEqual(result["text"], "mock response")

    def test_generate_response_with_system_prompt(self):
        result = self.agent.generate_response(prompt="test", system_prompt="be helpful")
        # The provider should receive messages with the system prompt first.
        args, kwargs = self.provider_mock.generate.call_args
        messages = args[0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "be helpful")
        self.assertEqual(result["text"], "mock response")

    def test_generate_response_with_history(self):
        history = [{"role": "assistant", "content": "previous answer"}]
        result = self.agent.generate_response(prompt="follow up", history=history)
        args, kwargs = self.provider_mock.generate.call_args
        messages = args[0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "assistant")
        self.assertEqual(messages[0]["content"], "previous answer")
        self.assertEqual(messages[1]["role"], "user")

    def test_generate_response_with_system_and_history(self):
        history = [{"role": "assistant", "content": "prev"}]
        result = self.agent.generate_response(
            prompt="q", system_prompt="sys", history=history
        )
        args, kwargs = self.provider_mock.generate.call_args
        messages = args[0]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")

    def test_generate_stream_returns_generator(self):
        gen = self.agent.generate_stream(prompt="stream test")
        # ``generate_stream`` should return a generator that yields the mocked
        # tokens from the provider.
        self.assertTrue(hasattr(gen, "__iter__"))
        tokens = list(gen)
        self.assertEqual(tokens, ["tok1", "tok2"])

    def test_generate_stream_with_system_and_history(self):
        history = [{"role": "assistant", "content": "prev"}]
        gen = self.agent.generate_stream(prompt="st", system_prompt="sys", history=history)
        args, kwargs = self.provider_mock.generate_stream.call_args
        messages = args[0]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")

    def test_summarize(self):
        self.provider_mock.generate.return_value = {
            "text": "summary text",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        summary = self.agent.summarize("long text to summarize")
        self.assertEqual(summary, "summary text")
        # Verify the provider was called with a summarization prompt containing the text
        args, kwargs = self.provider_mock.generate.call_args
        messages = args[0]
        self.assertEqual(len(messages), 1)
        self.assertIn("long text to summarize", messages[0]["content"])

    def test_search_and_answer_stream_uses_web_searcher(self):
        # Create a dummy WebSearcher that returns a known context and sources.
        dummy_searcher = MagicMock()
        dummy_searcher.search_and_format.return_value = ("context", [
            # ``SearchResult`` objects are not needed for this test – only the URL
            # attribute is accessed.
            type("Result", (), {"url": "https://example.com"})(),
        ])
        # Patch the agent's ``generate_stream`` to return a simple generator.
        self.agent.generate_stream = MagicMock(return_value=iter(["answer"]))

        gen, sources = self.agent.search_and_answer_stream(
            prompt="question",
            web_searcher=dummy_searcher,
            web_config=MagicMock(max_results=5),
        )
        # The generator should yield the mocked answer token.
        self.assertEqual(list(gen), ["answer"])
        # The source list should contain the URL from the dummy result.
        self.assertEqual(sources, ["https://example.com"])

    def test_search_and_answer_stream_with_system_and_history(self):
        dummy_searcher = MagicMock()
        dummy_searcher.search_and_format.return_value = ("context", [
            type("Result", (), {"url": "https://src"})(),
        ])
        self.agent.generate_stream = MagicMock(return_value=iter(["answer"]))

        gen, sources = self.agent.search_and_answer_stream(
            prompt="q",
            web_searcher=dummy_searcher,
            web_config=MagicMock(max_results=5),
            system_prompt="custom system",
            history=[{"role": "assistant", "content": "prev"}],
        )
        # Verify the augmented prompt includes context
        args, kwargs = self.agent.generate_stream.call_args
        self.assertIn("context", args[0].lower())  # The augmented prompt has "CONTEXT"
        # System prompt should be the custom one
        self.assertEqual(args[1], "custom system")

    def test_search_and_answer_search_failure_falls_back(self):
        """If web search fails, fall back to plain LLM with no sources."""
        dummy_searcher = MagicMock()
        dummy_searcher.search_and_format.side_effect = RuntimeError("search failed")
        self.agent.generate_stream = MagicMock(return_value=iter(["fallback"]))

        gen, sources = self.agent.search_and_answer_stream(
            prompt="q",
            web_searcher=dummy_searcher,
            web_config=MagicMock(max_results=5),
        )
        self.assertEqual(list(gen), ["fallback"])
        self.assertEqual(sources, [])  # No sources returned

    def test_search_and_answer_empty_context_falls_back(self):
        """If search returns no useful context, fall back to plain LLM."""
        dummy_searcher = MagicMock()
        dummy_searcher.search_and_format.return_value = ("", [])
        self.agent.generate_stream = MagicMock(return_value=iter(["direct answer"]))

        gen, sources = self.agent.search_and_answer_stream(
            prompt="q",
            web_searcher=dummy_searcher,
            web_config=MagicMock(max_results=5),
        )
        self.assertEqual(list(gen), ["direct answer"])
        self.assertEqual(sources, [])

    def test_search_and_answer_passes_system_prompt(self):
        """When context is available, the user-supplied system prompt should be used."""
        dummy_searcher = MagicMock()
        dummy_searcher.search_and_format.return_value = ("ctx", [
            type("Result", (), {"url": "https://src"})(),
        ])
        self.agent.generate_stream = MagicMock(return_value=iter(["answer"]))

        gen, sources = self.agent.search_and_answer_stream(
            prompt="q",
            web_searcher=dummy_searcher,
            web_config=MagicMock(max_results=5),
            system_prompt="custom system instruction",
        )
        args, kwargs = self.agent.generate_stream.call_args
        # The system_prompt parameter should be the custom one
        self.assertEqual(args[1], "custom system instruction")


class TestAgentInitialization(unittest.TestCase):
    """Test the NexusAgent constructor with various configurations."""

    def test_default_parameters(self):
        with patch("nexus.core.agent.create_provider") as mock_factory:
            agent = NexusAgent(api_key="key", model="m", provider="groq")
        mock_factory.assert_called_once()
        config = mock_factory.call_args[0][0]
        self.assertEqual(config.api_key, "key")
        self.assertEqual(config.model, "m")
        self.assertEqual(config.name, "groq")
        self.assertEqual(config.timeout, 30)
        self.assertEqual(config.max_tokens, 4096)
        self.assertEqual(config.temperature, 0.7)

    def test_custom_parameters(self):
        with patch("nexus.core.agent.create_provider") as mock_factory:
            agent = NexusAgent(
                api_key="key",
                model="gpt-4",
                provider="openai",
                base_url="https://custom.openai.com",
                timeout=60,
                max_tokens=2048,
                temperature=0.5,
            )
        config = mock_factory.call_args[0][0]
        self.assertEqual(config.name, "openai")
        self.assertEqual(config.model, "gpt-4")
        self.assertEqual(config.base_url, "https://custom.openai.com")
        self.assertEqual(config.timeout, 60)
        self.assertEqual(config.max_tokens, 2048)
        self.assertEqual(config.temperature, 0.5)

    def test_ollama_provider(self):
        with patch("nexus.core.agent.create_provider") as mock_factory:
            agent = NexusAgent(
                api_key="",
                model="llama3.2",
                provider="ollama",
            )
        config = mock_factory.call_args[0][0]
        self.assertEqual(config.name, "ollama")
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.base_url, "")


if __name__ == "__main__":
    unittest.main()