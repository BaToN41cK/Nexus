"""
Embedding model interface and implementations for Nexus RAG.

Provides a common :class:`EmbeddingModel` abstraction with:
  - :class:`SentenceTransformerEmbeddings` — local CPU-friendly embeddings.
  - :class:`OpenAIEmbeddings` — OpenAI API embeddings.
  - :class:`OllamaEmbeddings` — Ollama embeddings (via Ollama API).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class EmbeddingModel(ABC):
    """Abstract embedding model.  All implementations are thread-safe."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts into a list of vectors.

        Args:
            texts: List of strings to embed.

        Returns:
            List of float vectors, one per input text.
        """

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string.  Override for specialised logic."""
        return self.embed([text])[0]

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the model."""


# ---------------------------------------------------------------------------
# Sentence-Transformers (local, CPU)
# ---------------------------------------------------------------------------


class SentenceTransformerEmbeddings(EmbeddingModel):
    """
    Local embedding model via `sentence-transformers`.

    Uses the ``all-MiniLM-L6-v2`` model by default (~80 MB, 384 dims,
    good balance of speed/quality).  Can be changed via the ``model_name``
    argument.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
        **kwargs: Any,
    ):
        self.model_name = model_name
        self.device = device
        self._model: Optional[Any] = None
        self._dimension: Optional[int] = None
        self._kwargs = kwargs
        logger.info("SentenceTransformerEmbeddings: model=%s device=%s", model_name, device)

    def _lazy_load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for local embeddings. "
                "Install with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(self.model_name, device=self.device, **self._kwargs)
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(
            "Loaded sentence-transformers model: %s (dim=%d, device=%s)",
            self.model_name, self._dimension, self.device,
        )

    @property
    def dimension(self) -> int:
        self._lazy_load()
        assert self._dimension is not None
        return self._dimension

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._lazy_load()
        assert self._model is not None
        embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()

    def close(self) -> None:
        self._model = None
        self._dimension = None


# ---------------------------------------------------------------------------
# OpenAI API
# ---------------------------------------------------------------------------


class OpenAIEmbeddings(EmbeddingModel):
    """
    OpenAI API embedding model.

    Uses ``text-embedding-3-small`` by default (1536 dims).  Supports
    ``text-embedding-3-large`` (3072 dims) and ``text-embedding-ada-002``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._kwargs = kwargs
        self._dimension = 1536  # default for text-embedding-3-small
        if "3-large" in model:
            self._dimension = 3072
        elif "ada" in model:
            self._dimension = 1536
        self._client: Optional[Any] = None
        logger.info("OpenAIEmbeddings: model=%s dim=%d", model, self._dimension)

    def _lazy_load(self) -> None:
        if self._client is not None:
            return
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAI embeddings. "
                "Install with: pip install openai"
            ) from exc
        kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = openai.OpenAI(**kwargs)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._lazy_load()
        assert self._client is not None
        # OpenAI API has a batch limit; handle small batches.
        batch_size = 2048
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self._client.embeddings.create(input=batch, model=self.model)
            # Sort by index to preserve order.
            sorted_data = sorted(resp.data, key=lambda x: x.index)
            all_embeddings.extend([d.embedding for d in sorted_data])
        return all_embeddings

    def close(self) -> None:
        self._client = None


# ---------------------------------------------------------------------------
# Ollama (local API)
# ---------------------------------------------------------------------------


class OllamaEmbeddings(EmbeddingModel):
    """
    Ollama embeddings via the Ollama API.

    Uses ``nomic-embed-text`` by default (768 dims).  Uses the ``requests``
    library that is already installed in Nexus.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dimension = 768  # nomic-embed-text default
        self._session: Optional[Any] = None
        logger.info("OllamaEmbeddings: model=%s url=%s", model, base_url)

    def _lazy_load(self) -> None:
        if self._session is not None:
            return
        import requests
        self._session = requests.Session()

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._lazy_load()
        assert self._session is not None
        import requests

        all_embeddings: List[List[float]] = []
        for text in texts:
            resp = self._session.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=60,
            )
            resp.raise_for_status()
            all_embeddings.append(resp.json()["embedding"])
        if all_embeddings:
            self._dimension = len(all_embeddings[0])
        return all_embeddings

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


# ---------------------------------------------------------------------------
# Factory with custom backend registration
# ---------------------------------------------------------------------------


_EMBEDDING_BACKENDS: Dict[str, Any] = {}


def register_embedding_backend(name: str, constructor: Any) -> None:
    """Register a custom embedding backend for use with :func:`create_embedding_model`."""
    _EMBEDDING_BACKENDS[name.lower().replace("-", "_")] = constructor


def create_embedding_model(
    backend: str = "sentence-transformers",
    **kwargs: Any,
) -> EmbeddingModel:
    """
    Build an embedding model by name.

    Built-in backends:
        - ``"sentence-transformers"`` (alias ``"local"``)
        - ``"openai"`` (alias ``"open-ai"``)
        - ``"ollama"``

    Custom backends can be registered via :func:`register_embedding_backend`.

    Args:
        backend: Backend name.
        **kwargs: Forwarded to the model constructor.

    Returns:
        An :class:`EmbeddingModel` instance.
    """
    backend_key = (backend or "sentence-transformers").lower().replace("-", "_")

    if backend_key in _EMBEDDING_BACKENDS:
        return _EMBEDDING_BACKENDS[backend_key](**kwargs)

    if backend_key in ("sentence_transformers", "local", "sentence-transformer"):
        return SentenceTransformerEmbeddings(**kwargs)
    if backend_key in ("openai", "open-ai"):
        return OpenAIEmbeddings(**kwargs)
    if backend_key in ("ollama",):
        return OllamaEmbeddings(**kwargs)

    raise ValueError(
        f"Unknown embedding backend: {backend!r}. "
        f"Use 'sentence-transformers', 'openai', 'ollama', "
        f"or a registered custom backend."
    )
