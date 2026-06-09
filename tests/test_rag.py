"""Tests for the Nexus RAG (Retrieval-Augmented Generation) pipeline.

Tests cover:
  - Embedding model interface
  - Vector store (FAISS) operations
  - BM25 retrieval
  - Hybrid search
  - MMR re-ranking
  - Document chunking
  - RAG engine integration
"""

import os
import tempfile
import unittest
from typing import Any, List

from nexus.core.embeddings import EmbeddingModel, create_embedding_model
from nexus.core.vector_store import (
    Document,
    SearchResult,
    VectorStore,
    create_vector_store,
    FaissVectorStore,
)
from nexus.core.retrieval import (
    BM25Retriever,
    CrossEncoderReranker,
    hybrid_search,
    max_marginal_relevance,
)
from nexus.core.rag import (
    ChunkConfig,
    RAGConfig,
    RAGEngine,
    RetrievalResult,
    chunk_text,
)


# ---------------------------------------------------------------------------
# Dummy embedding model for testing (no external dependencies)
# ---------------------------------------------------------------------------


class DummyEmbeddings(EmbeddingModel):
    """Simple deterministic embedding model for tests.

    Embeds each text as a vector of length ``dim`` where each element is
    the sum of character codes of the text, normalised.
    """

    def __init__(self, dim: int = 4):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        import math
        results: List[List[float]] = []
        for text in texts:
            val = sum(ord(c) for c in text) % 1000 / 1000.0
            # Create a vector where first element is signature and rest small.
            vec = [val] + [0.01 * i for i in range(self._dim - 1)]
            # Normalise.
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            results.append(vec)
        return results

    def close(self) -> None:
        pass


def _dummy_factory(**kwargs: Any) -> EmbeddingModel:
    return DummyEmbeddings(**kwargs)


# Register dummy backend for RAG engine tests.
from nexus.core.embeddings import register_embedding_backend  # noqa: E402
register_embedding_backend("dummy", _dummy_factory)


# ---------------------------------------------------------------------------
# Tests: Embedding Model
# ---------------------------------------------------------------------------


class TestEmbeddingModel(unittest.TestCase):
    def test_dummy_embeddings_dimension(self):
        model = DummyEmbeddings(dim=8)
        self.assertEqual(model.dimension, 8)

    def test_dummy_embeddings_embed_single(self):
        model = DummyEmbeddings(dim=4)
        vec = model.embed_query("hello world")
        self.assertEqual(len(vec), 4)
        # Should be normalised (length ≈ 1.0).
        import math
        norm = math.sqrt(sum(v * v for v in vec))
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_dummy_embeddings_embed_batch(self):
        model = DummyEmbeddings(dim=4)
        texts = ["hello", "world", "test"]
        vecs = model.embed(texts)
        self.assertEqual(len(vecs), 3)
        for v in vecs:
            self.assertEqual(len(v), 4)


# ---------------------------------------------------------------------------
# Tests: Vector Store
# ---------------------------------------------------------------------------


class TestFaissVectorStore(unittest.TestCase):
    def setUp(self):
        self.store = FaissVectorStore(dimension=4)

    def _add_docs(self):
        docs = [
            Document(text="Nexus is an AI assistant", metadata={"source": "readme"}),
            Document(text="It supports multiple LLM providers", metadata={"source": "docs"}),
            Document(text="RAG adds retrieval capabilities", metadata={"source": "rag_doc"}),
        ]
        emb = DummyEmbeddings(dim=4).embed([d.text for d in docs])
        self.store.add(docs, emb)
        return docs

    def test_empty_search(self):
        results = self.store.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        self.assertEqual(len(results), 0)

    def test_add_and_search(self):
        self._add_docs()
        self.assertEqual(self.store.count(), 3)

        query_emb = DummyEmbeddings(dim=4).embed_query("Nexus assistant")
        results = self.store.search(query_emb, top_k=2)
        self.assertGreaterEqual(len(results), 1)

    def test_clear(self):
        self._add_docs()
        self.assertEqual(self.store.count(), 3)
        self.store.clear()
        self.assertEqual(self.store.count(), 0)

    def test_save_and_load(self):
        self._add_docs()
        with tempfile.NamedTemporaryFile(suffix=".faiss", delete=False) as f:
            path = f.name
        try:
            self.store.save(path)
            # Create a new store and load.
            new_store = FaissVectorStore(dimension=4)
            new_store.load(path)
            self.assertEqual(new_store.count(), 3)
        finally:
            os.unlink(path)
            meta_path = path + ".meta.json"
            if os.path.isfile(meta_path):
                os.unlink(meta_path)

    def test_delete(self):
        docs = self._add_docs()
        # Delete first doc.
        self.store.delete([docs[0].id])
        self.assertEqual(self.store.count(), 2)


# ---------------------------------------------------------------------------
# Tests: BM25 Retrieval
# ---------------------------------------------------------------------------


class TestBM25Retriever(unittest.TestCase):
    def setUp(self):
        self.bm25 = BM25Retriever()

    def test_empty_search(self):
        results = self.bm25.search("test query")
        self.assertEqual(len(results), 0)

    def test_basic_search(self):
        docs = [
            Document(text="Nexus is an AI assistant for developers"),
            Document(text="RAG means Retrieval Augmented Generation"),
            Document(text="The assistant supports multiple LLM providers"),
        ]
        self.bm25.add_documents(docs)
        results = self.bm25.search("AI assistant", top_k=2)
        self.assertGreaterEqual(len(results), 1)
        # "AI" and "assistant" should match first doc.
        self.assertIn("assistant", results[0].document.text.lower())

    def test_clear(self):
        docs = [Document(text="some text")]
        self.bm25.add_documents(docs)
        self.assertEqual(self.bm25.doc_count, 1)
        self.bm25.clear()
        self.assertEqual(self.bm25.doc_count, 0)

    def test_multiple_docs_scoring(self):
        docs = [
            Document(text="Python programming language"),
            Document(text="JavaScript for web development"),
            Document(text="Python is great for data science"),
        ]
        self.bm25.add_documents(docs)
        results = self.bm25.search("python", top_k=3)
        self.assertEqual(len(results), 2)  # two docs contain "python"
        self.assertGreater(results[0].score, 0)


# ---------------------------------------------------------------------------
# Tests: Hybrid Search
# ---------------------------------------------------------------------------


class TestHybridSearch(unittest.TestCase):
    def test_empty_inputs(self):
        result = hybrid_search([], [])
        self.assertEqual(len(result), 0)

    def test_only_vector(self):
        docs = [Document(text="test")]
        vector_res = [SearchResult(document=docs[0], score=0.9)]
        result = hybrid_search(vector_res, [])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].score, 0.9)

    def test_only_bm25(self):
        docs = [Document(text="test")]
        bm25_res = [SearchResult(document=docs[0], score=2.5)]
        result = hybrid_search([], bm25_res)
        self.assertEqual(len(result), 1)

    def test_hybrid_combines_results(self):
        doc_a = Document(text="AI assistant", id="a")
        doc_b = Document(text="RAG system", id="b")

        vector_res = [SearchResult(document=doc_a, score=0.9)]
        bm25_res = [SearchResult(document=doc_b, score=3.0)]

        result = hybrid_search(vector_res, bm25_res, alpha=0.5)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# Tests: MMR
# ---------------------------------------------------------------------------


class TestMaxMarginalRelevance(unittest.TestCase):
    def test_empty_results(self):
        result = max_marginal_relevance([], [], [0.1, 0.2], top_k=3)
        self.assertEqual(len(result), 0)

    def test_mmr_selects_diverse(self):
        docs = [
            Document(text="Python is a programming language"),
            Document(text="Python is great for AI and ML"),
            Document(text="JavaScript is for web development"),
        ]
        emb_model = DummyEmbeddings(dim=4)
        embeddings = emb_model.embed([d.text for d in docs])
        query_emb = emb_model.embed_query("programming languages")

        results = [
            SearchResult(document=doc, score=0.9)
            for doc in docs
        ]

        mmr_results = max_marginal_relevance(
            results, embeddings, query_emb, top_k=2, lambda_param=0.5,
        )
        self.assertGreaterEqual(len(mmr_results), 1)


# ---------------------------------------------------------------------------
# Tests: Document Chunking
# ---------------------------------------------------------------------------


class TestChunking(unittest.TestCase):
    def test_empty_text(self):
        chunks = chunk_text("", ChunkConfig())
        self.assertEqual(len(chunks), 0)

    def test_small_text_no_chunking(self):
        text = "Hello world."
        config = ChunkConfig(chunk_size=512, chunk_overlap=0)
        chunks = chunk_text(text, config)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, text)

    def test_large_text_split(self):
        text = "Word. " * 200  # ~1200 chars
        config = ChunkConfig(chunk_size=200, chunk_overlap=20)
        chunks = chunk_text(text, config)
        self.assertGreater(len(chunks), 1)

    def test_chunk_source_metadata(self):
        text = "Test content here. " * 50
        chunks = chunk_text(text, ChunkConfig(chunk_size=100, chunk_overlap=10), source="test.txt")
        for chunk in chunks:
            self.assertEqual(chunk.metadata.get("source"), "test.txt")


# ---------------------------------------------------------------------------
# Tests: RAG Engine
# ---------------------------------------------------------------------------


class TestRAGEngine(unittest.TestCase):
    def setUp(self):
        self.config = RAGConfig(
            embedding_backend="dummy",
            embedding_kwargs={"dim": 4},
            vector_store_backend="faiss",
            vector_store_kwargs={"dimension": 4},
            chunk_config=ChunkConfig(chunk_size=200, chunk_overlap=20),
            top_k_initial=5,
            top_k_after_rerank=3,
            use_bm25=True,
            use_mmr=True,
            use_cross_encoder=False,
        )
        self.engine = RAGEngine(config=self.config)

    def test_empty_index(self):
        results = self.engine.retrieve("test query")
        self.assertEqual(len(results), 0)

    def test_index_and_retrieve(self):
        count = self.engine.index_texts([
            ("Nexus is an AI assistant with web search capabilities. "
             "It supports multiple LLM providers including Groq, OpenAI, and Anthropic.",
             {"source": "readme.md"}),
            ("RAG (Retrieval-Augmented Generation) enhances LLM responses "
             "by retrieving relevant context from a knowledge base.",
             {"source": "docs/rag.md"}),
        ])
        self.assertGreater(count, 0)
        self.assertGreater(self.engine.doc_count, 0)

        results = self.engine.retrieve("What is Nexus?", top_k=3)
        self.assertGreater(len(results), 0)

    def test_query_without_agent_returns_citations(self):
        self.engine.index_texts([
            ("Nexus is an AI assistant.", {"source": "readme.md"}),
        ])
        result = self.engine.query("What is Nexus?")
        self.assertIsInstance(result, RetrievalResult)
        self.assertGreater(len(result.source_documents), 0)
        self.assertGreater(len(result.citations), 0)
        for citation in result.citations:
            self.assertIn("source", citation)
            self.assertIn("score", citation)

    def test_clear(self):
        self.engine.index_texts([
            ("Nexus is an AI assistant.", {"source": "readme.md"}),
        ])
        self.assertGreater(self.engine.doc_count, 0)
        self.engine.clear()
        self.assertEqual(self.engine.doc_count, 0)

    def test_save_and_load(self):
        self.engine.index_texts([
            ("Nexus is an AI assistant.", {"source": "readme.md"}),
        ])
        with tempfile.NamedTemporaryFile(suffix=".faiss", delete=False) as f:
            path = f.name
        try:
            self.engine.save(path)
            # Create new engine and load.
            engine2 = RAGEngine(config=self.config)
            engine2.load(path)
            self.assertEqual(engine2.doc_count, self.engine.doc_count)
        finally:
            os.unlink(path)
            meta_path = path + ".meta.json"
            if os.path.isfile(meta_path):
                os.unlink(meta_path)

    def test_index_documents_directly(self):
        docs = [
            Document(text="Nexus supports multiple providers.", metadata={"source": "docs.md"}),
        ]
        count = self.engine.index_documents(docs)
        self.assertEqual(count, 1)
        self.assertEqual(self.engine.doc_count, 1)


# ---------------------------------------------------------------------------
# Tests: RAGConfig defaults
# ---------------------------------------------------------------------------


class TestRAGConfig(unittest.TestCase):
    def test_default_config(self):
        config = RAGConfig()
        self.assertEqual(config.embedding_backend, "sentence-transformers")
        self.assertEqual(config.vector_store_backend, "faiss")
        self.assertTrue(config.use_bm25)
        self.assertTrue(config.use_mmr)
        self.assertFalse(config.use_cross_encoder)
        self.assertEqual(config.top_k_initial, 20)
        self.assertEqual(config.top_k_after_rerank, 5)

    def test_custom_config(self):
        config = RAGConfig(
            embedding_backend="openai",
            vector_store_backend="chroma",
            use_bm25=False,
        )
        self.assertEqual(config.embedding_backend, "openai")
        self.assertEqual(config.vector_store_backend, "chroma")
        self.assertFalse(config.use_bm25)


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()