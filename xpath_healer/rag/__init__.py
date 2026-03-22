"""Optional RAG adapters (disabled by default)."""

from xpath_healer.rag.embedder import Embedder
from xpath_healer.rag.llm import LLM
from xpath_healer.rag.chroma_retriever import ChromaRetriever
from xpath_healer.rag.openai_embedder import OpenAIEmbedder
from xpath_healer.rag.openai_llm import OpenAILLM
from xpath_healer.rag.pgvector_retriever import PgVectorRetriever
from xpath_healer.rag.rag_assist import RagAssist
from xpath_healer.rag.retriever import Retriever

__all__ = [
    "Embedder",
    "Retriever",
    "LLM",
    "RagAssist",
    "OpenAIEmbedder",
    "OpenAILLM",
    "ChromaRetriever",
    "PgVectorRetriever",
]
