"""Backward-compatible retriever alias.

This module keeps the historical class name while routing all vector retrieval
to ChromaDB.
"""

from xpath_healer.rag.chroma_retriever import ChromaRetriever


class PgVectorRetriever(ChromaRetriever):
    """Compatibility alias for legacy imports."""

    def __init__(
        self,
        dsn: str = "",
        app_id: str = "",
        page_name: str = "",
        field_type: str = "",
        pool_min_size: int = 1,
        pool_max_size: int = 5,
        chroma_path: str = "",
        rag_collection: str = "",
        elements_collection: str = "",
    ) -> None:
        _ = dsn
        _ = pool_min_size
        _ = pool_max_size
        super().__init__(
            chroma_path=chroma_path,
            rag_collection=rag_collection,
            elements_collection=elements_collection,
            app_id=app_id,
            page_name=page_name,
            field_type=field_type,
        )
