"""
Retrieval module for Nexus RAG.

Provides:
  - :class:`BM25Retriever` — keyword-based retrieval using BM25 (Okapi).
  - :func:`max_marginal_relevance` — MMR re-ranking for diversity.
  - :func:`hybrid_search` — combine BM25 + vector search scores.
  - :class:`CrossEncoderReranker` — neural re-ranking via cross-encoders.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from nexus.core.vector_store import Document, SearchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r"\w+", text.lower())


def _compute_idf(corpus: List[str]) -> Dict[str, float]:
    """Compute IDF for all terms across the corpus."""
    doc_count = len(corpus)
    df: Counter[str] = Counter()
    for doc in corpus:
        terms = set(_tokenize(doc))
        df.update(terms)
    idf: Dict[str, float] = {}
    for term, freq in df.items():
        idf[term] = math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
    return idf


# ---------------------------------------------------------------------------
# BM25
# ---------------------------------------------------------------------------


class BM25Retriever:
    """
    Okapi BM25 retrieval from a set of documents.

    Thread-safe.  Supports adding documents incrementally.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._lock = threading.Lock()
        self._documents: List[Document] = []
        self._doc_texts: List[str] = []
        self._avgdl: float = 0.0
        self._idf: Dict[str, float] = {}

    def add_documents(self, documents: List[Document]) -> None:
        """Add documents to the BM25 index."""
        with self._lock:
            for doc in documents:
                self._documents.append(doc)
                self._doc_texts.append(doc.text)
            self._rebuild_stats()

    def _rebuild_stats(self) -> None:
        """Rebuild IDF and avgdl after adding documents."""
        if not self._doc_texts:
            self._avgdl = 0.0
            self._idf = {}
            return
        total_length = sum(len(_tokenize(t)) for t in self._doc_texts)
        self._avgdl = total_length / len(self._doc_texts)
        self._idf = _compute_idf(self._doc_texts)

    def search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """
        Search documents using BM25 scoring.

        Args:
            query: The search query.
            top_k: Number of results to return.

        Returns:
            List of SearchResult sorted by BM25 score descending.
        """
        if not self._documents:
            return []

        query_terms = _tokenize(query)
        if not query_terms:
            return []

        with self._lock:
            scores: List[Tuple[float, int]] = []
            for i, doc_text in enumerate(self._doc_texts):
                score = self._bm25_score(query_terms, doc_text)
                if score > 0:
                    scores.append((score, i))

        scores.sort(key=lambda x: x[0], reverse=True)
        results: List[SearchResult] = []
        for score, idx in scores[:top_k]:
            results.append(SearchResult(document=self._documents[idx], score=score))
        return results

    def _bm25_score(self, query_terms: List[str], doc_text: str) -> float:
        """Compute BM25 score for a single document."""
        doc_terms = _tokenize(doc_text)
        doc_len = len(doc_terms)
        if doc_len == 0:
            return 0.0

        tf_counter = Counter(doc_terms)
        score = 0.0
        for term in query_terms:
            if term not in self._idf:
                continue
            tf = tf_counter.get(term, 0)
            if tf == 0:
                continue
            idf = self._idf[term]
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / self._avgdl))
            score += idf * numerator / denominator
        return score

    @property
    def doc_count(self) -> int:
        """Return the number of indexed documents."""
        return len(self._documents)

    def clear(self) -> None:
        """Remove all documents from the index."""
        with self._lock:
            self._documents.clear()
            self._doc_texts.clear()
            self._avgdl = 0.0
            self._idf = {}


# ---------------------------------------------------------------------------
# Hybrid Search (BM25 + Vector)
# ---------------------------------------------------------------------------


def _reciprocal_rank_fusion(
    vector_results: List[SearchResult],
    bm25_results: List[SearchResult],
    k: float = 60.0,
    alpha: float = 0.5,
) -> List[SearchResult]:
    """
    Combine vector and BM25 results using Reciprocal Rank Fusion (RRF).

    Args:
        vector_results: Results from vector search.
        bm25_results: Results from BM25 search.
        k: RRF constant (default 60).
        alpha: Weight for vector scores (0 = pure BM25, 1 = pure vector).

    Returns:
        Re-ranked list of SearchResult with fused scores.
    """
    # Build doc_id -> RRF score maps.
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Document] = {}

    for rank, res in enumerate(vector_results):
        doc_id = res.document.id
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + alpha * (1.0 / (k + rank + 1))
        doc_map[doc_id] = res.document

    for rank, res in enumerate(bm25_results):
        doc_id = res.document.id
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1 - alpha) * (1.0 / (k + rank + 1))
        doc_map[doc_id] = res.document

    # Sort by fused score descending.
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    return [
        SearchResult(document=doc_map[doc_id], score=rrf_scores[doc_id])
        for doc_id in sorted_ids
    ]


def hybrid_search(
    vector_results: List[SearchResult],
    bm25_results: List[SearchResult],
    alpha: float = 0.5,
    rrf_k: float = 60.0,
) -> List[SearchResult]:
    """
    Combine BM25 and vector search results via RRF.

    Args:
        vector_results: Results from vector similarity search.
        bm25_results: Results from BM25 keyword search.
        alpha: Weight (0 = pure BM25, 1 = pure vector).
        rrf_k: RRF constant.

    Returns:
        Combined results sorted by fused score.
    """
    if not vector_results and not bm25_results:
        return []
    if not vector_results:
        return bm25_results
    if not bm25_results:
        return vector_results

    return _reciprocal_rank_fusion(vector_results, bm25_results, k=rrf_k, alpha=alpha)


# ---------------------------------------------------------------------------
# Max Marginal Relevance (MMR)
# ---------------------------------------------------------------------------


def max_marginal_relevance(
    results: List[SearchResult],
    embeddings: List[List[float]],
    query_embedding: List[float],
    top_k: int = 5,
    lambda_param: float = 0.5,
    diversity_threshold: float = 0.8,
) -> List[SearchResult]:
    """
    Re-rank results using Max Marginal Relevance for diversity.

    Selects a subset of results that balances relevance to the query
    (high similarity) with diversity (low similarity to already-selected items).

    Args:
        results: Initial search results.
        embeddings: Corresponding embedding vectors for each result.
        query_embedding: Query embedding vector.
        top_k: Number of results to return.
        lambda_param: Balance between relevance (1.0) and diversity (0.0).
        diversity_threshold: Minimum similarity threshold to consider.

    Returns:
        Re-ranked list with diverse results.
    """
    if not results or not embeddings:
        return results[:top_k]

    import math

    def cosine_sim(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # Normalise query embedding.
    query_norm = query_embedding
    q_norm_len = math.sqrt(sum(x * x for x in query_norm))
    if q_norm_len > 0:
        query_norm = [x / q_norm_len for x in query_norm]

    # Pre-compute relevance scores.
    relevance = [cosine_sim(query_norm, emb) for emb in embeddings]

    # Greedy MMR selection.
    selected: List[int] = []
    candidate_indices = list(range(len(results)))

    for _ in range(min(top_k, len(results))):
        if not candidate_indices:
            break

        mmr_scores = []
        for idx in candidate_indices:
            # Relevance term.
            mmr = lambda_param * relevance[idx]

            # Diversity term.
            if selected:
                max_sim = max(
                    cosine_sim(embeddings[idx], embeddings[s])
                    for s in selected
                )
                mmr -= (1 - lambda_param) * max_sim

            mmr_scores.append(mmr)

        # Select best index.
        best_idx = candidate_indices[mmr_scores.index(max(mmr_scores))]
        selected.append(best_idx)
        candidate_indices.remove(best_idx)

    return [results[i] for i in selected]


# ---------------------------------------------------------------------------
# Cross-Encoder Re-ranker
# ---------------------------------------------------------------------------


class CrossEncoderReranker:
    """
    Neural re-ranker using a cross-encoder model.

    Uses a lightweight model (e.g. ``cross-encoder/ms-marco-MiniLM-L-6-v2``)
    that jointly encodes (query, document) pairs for more accurate scoring.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model: Optional[Any] = None
        self._lock = threading.Lock()

    def _lazy_load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for CrossEncoderReranker. "
                "Install with: pip install sentence-transformers"
            ) from exc
        self._model = CrossEncoder(self.model_name)

    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        top_k: Optional[int] = None,
    ) -> List[SearchResult]:
        """
        Re-rank results using the cross-encoder.

        Args:
            query: The original query.
            results: Initial search results to re-rank.
            top_k: Number of results to return (default: all).

        Returns:
            Re-ranked list of SearchResult.
        """
        if not results:
            return []

        self._lazy_load()
        assert self._model is not None

        # Prepare pairs.
        pairs = [(query, res.document.text) for res in results]

        with self._lock:
            scores = self._model.predict(pairs)

        # Attach scores to results.
        scored_results = list(zip(scores, results))

        # Sort by score descending.
        scored_results.sort(key=lambda x: x[0], reverse=True)

        k = top_k if top_k is not None else len(results)
        return [
            SearchResult(document=res.document, score=float(score))
            for score, res in scored_results[:k]
        ]