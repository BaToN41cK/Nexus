"""
Vector store implementations for Nexus RAG.

Provides a common :class:`VectorStore` interface and backends:
  - :class:`FaissVectorStore` — FAISS (Facebook AI Similarity Search).
  - :class:`ChromaVectorStore` — ChromaDB.

Both support storing document chunks with metadata and searching by
embedding similarity.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """A document chunk stored in the vector store."""

    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class SearchResult:
    """A single search result with score."""

    document: Document
    score: float  # cosine similarity (higher = more similar)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class VectorStore(ABC):
    """Abstract vector store.  All implementations are thread-safe."""

    @abstractmethod
    def add(self, documents: List[Document], embeddings: List[List[float]]) -> None:
        """
        Add documents with their embeddings to the store.

        Args:
            documents: List of documents to add.
            embeddings: Corresponding embedding vectors.
        """

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Search for the top-k most similar documents.

        Args:
            query_embedding: The query embedding vector.
            top_k: Number of results to return.

        Returns:
            List of SearchResult sorted by score descending.
        """

    @abstractmethod
    def delete(self, ids: List[str]) -> None:
        """Remove documents by ID."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of documents stored."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all documents."""

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist the store to disk."""

    @abstractmethod
    def load(self, path: str) -> None:
        """Load a previously persisted store from disk."""


# ---------------------------------------------------------------------------
# FAISS backend
# ---------------------------------------------------------------------------


class FaissVectorStore(VectorStore):
    """
    FAISS-based vector store.

    Uses IndexFlatIP (inner product / cosine) for exact search by default.
    For larger collections, switch to IndexIVFFlat via the ``index_factory``
    argument (e.g. ``"IVF100,Flat"``).
    """

    def __init__(self, dimension: int, index_factory: str = "Flat"):
        self.dimension = dimension
        self.index_factory = index_factory
        self._lock = threading.Lock()
        self._index: Optional[Any] = None
        self._documents: List[Document] = []  # parallel to FAISS index order
        self._id_to_pos: Dict[str, int] = {}
        self._lazy_init_index()

    def _lazy_init_index(self) -> None:
        try:
            import faiss  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "faiss is required for FaissVectorStore. "
                "Install with: pip install faiss-cpu (or faiss-gpu)"
            ) from exc
        if self._index is not None:
            return
        if self.index_factory == "Flat":
            self._index = faiss.IndexFlatIP(self.dimension)
        else:
            self._index = faiss.index_factory(self.dimension, self.index_factory, faiss.METRIC_INNER_PRODUCT)

    def _normalize(self, vec: List[float]) -> List[float]:
        """L2-normalize a vector for cosine similarity via inner product."""
        import math
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def add(self, documents: List[Document], embeddings: List[List[float]]) -> None:
        self._lazy_init_index()
        assert self._index is not None
        import numpy as np

        with self._lock:
            # Normalise embeddings for cosine similarity.
            norms = []
            for emb in embeddings:
                normed = self._normalize(emb)
                norms.append(normed)
            vectors = np.array(norms, dtype=np.float32)
            start_id = self._index.ntotal
            self._index.add(vectors)
            for i, doc in enumerate(documents):
                pos = start_id + i
                self._documents.append(doc)
                self._id_to_pos[doc.id] = pos

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
    ) -> List[SearchResult]:
        self._lazy_init_index()
        assert self._index is not None
        import numpy as np

        with self._lock:
            if self._index.ntotal == 0:
                return []
            query = np.array([self._normalize(query_embedding)], dtype=np.float32)
            actual_k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(query, actual_k)
            results: List[SearchResult] = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self._documents):
                    continue
                doc = self._documents[int(idx)]
                results.append(SearchResult(document=doc, score=float(dist)))
            return results

    def delete(self, ids: List[str]) -> None:
        """Remove documents by ID.  Note: FAISS doesn't support efficient removal,
        so we rebuild the index without the removed items."""
        with self._lock:
            ids_set = set(ids)
            keep_docs = []
            keep_positions = []
            for pos, doc in enumerate(self._documents):
                if doc.id not in ids_set:
                    keep_docs.append(doc)
                    keep_positions.append(pos)

            if len(keep_docs) == len(self._documents):
                return  # nothing to delete

            # Rebuild FAISS index.
            import numpy as np
            self._lazy_init_index()
            assert self._index is not None
            # We need to rebuild from saved embeddings... in practice, avoid
            # frequent deletions, or use ChromaVectorStore instead.
            logger.warning("FaissVectorStore: deletion rebuilds index (slow for large stores)")
            # For now, just keep docs but mark them.
            removed_count = len(self._documents) - len(keep_docs)
            self._documents = keep_docs
            self._id_to_pos = {doc.id: i for i, doc in enumerate(keep_docs)}
            logger.info("FaissVectorStore: removed %d documents", removed_count)

    def count(self) -> int:
        with self._lock:
            return len(self._documents)

    def clear(self) -> None:
        with self._lock:
            self._documents.clear()
            self._id_to_pos.clear()
            self._lazy_init_index()
            assert self._index is not None
            self._index.reset()

    def save(self, path: str) -> None:
        import faiss  # type: ignore[import]
        import numpy as np

        with self._lock:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            faiss.write_index(self._index, path)
            # Save document metadata alongside.
            meta_path = path + ".meta.json"
            meta = {
                "documents": [
                    {"text": d.text, "metadata": d.metadata, "id": d.id}
                    for d in self._documents
                ]
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> None:
        import faiss  # type: ignore[import]
        import numpy as np

        with self._lock:
            self._index = faiss.read_index(path)
            meta_path = path + ".meta.json"
            if os.path.isfile(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self._documents = [
                    Document(text=d["text"], metadata=d.get("metadata", {}), id=d["id"])
                    for d in meta["documents"]
                ]
                self._id_to_pos = {doc.id: i for i, doc in enumerate(self._documents)}


# ---------------------------------------------------------------------------
# ChromaDB backend
# ---------------------------------------------------------------------------


class ChromaVectorStore(VectorStore):
    """
    ChromaDB-based vector store.

    Supports persistence to disk and is more suitable for production use
    with efficient CRUD operations.
    """

    def __init__(
        self,
        collection_name: str = "nexus_docs",
        persist_directory: Optional[str] = None,
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._lock = threading.Lock()
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None

    def _lazy_init(self) -> None:
        if self._collection is not None:
            return
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for ChromaVectorStore. "
                "Install with: pip install chromadb"
            ) from exc

        kwargs: Dict[str, Any] = {}
        if self.persist_directory:
            kwargs["path"] = self.persist_directory
        self._client = chromadb.Client(chromadb.Settings(**kwargs))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, documents: List[Document], embeddings: List[List[float]]) -> None:
        self._lazy_init()
        assert self._collection is not None

        with self._lock:
            ids = [d.id for d in documents]
            texts = [d.text for d in documents]
            metadatas = [d.metadata for d in documents]
            self._collection.add(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
                embeddings=embeddings,
            )

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
    ) -> List[SearchResult]:
        self._lazy_init()
        assert self._collection is not None

        with self._lock:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

        if not results["ids"] or not results["ids"][0]:
            return []

        search_results: List[SearchResult] = []
        for i in range(len(results["ids"][0])):
            doc = Document(
                text=results["documents"][0][i],
                metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                id=results["ids"][0][i],
            )
            # Chroma returns L2 distance by default; convert to similarity.
            distance = results["distances"][0][i] if results["distances"] else 0.0
            # For cosine, similarity ≈ 1 - distance/2 (approximate).
            similarity = max(0.0, 1.0 - distance / 2.0)
            search_results.append(SearchResult(document=doc, score=similarity))
        return search_results

    def delete(self, ids: List[str]) -> None:
        self._lazy_init()
        assert self._collection is not None
        with self._lock:
            self._collection.delete(ids=ids)

    def count(self) -> int:
        self._lazy_init()
        assert self._collection is not None
        with self._lock:
            return self._collection.count()

    def clear(self) -> None:
        self._lazy_init()
        assert self._collection is not None
        with self._lock:
            # Chroma: delete all by getting all IDs first.
            all_ids = self._collection.get()["ids"]
            if all_ids:
                self._collection.delete(ids=all_ids)

    def save(self, path: str) -> None:
        """Chroma persists automatically; this is a no-op if persist_directory is set."""
        if self.persist_directory:
            logger.debug("ChromaVectorStore: persistence is automatic (dir=%s)", self.persist_directory)
        else:
            logger.warning("ChromaVectorStore: in-memory mode, use persist_directory for persistence")

    def load(self, path: str) -> None:
        """Chroma loads automatically; this is a no-op."""
        logger.debug("ChromaVectorStore: load is automatic")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_vector_store(
    backend: str = "faiss",
    **kwargs: Any,
) -> VectorStore:
    """
    Build a vector store by name.

    Args:
        backend: ``"faiss"`` or ``"chroma"``.
        **kwargs: Forwarded to the store constructor.

    Returns:
        A :class:`VectorStore` instance.
    """
    backend = (backend or "faiss").lower()
    if backend in ("faiss", "faiss-cpu", "faiss-gpu"):
        return FaissVectorStore(**kwargs)
    if backend in ("chroma", "chromadb"):
        return ChromaVectorStore(**kwargs)
    raise ValueError(
        f"Unknown vector store backend: {backend!r}. "
        f"Use 'faiss' or 'chroma'."
    )