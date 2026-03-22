from xpath_healer.store.pg_repository import PostgresMetadataRepository


def test_schema_sql_contains_required_tables_and_indexes() -> None:
    sql = PostgresMetadataRepository.schema_sql()
    assert "CREATE TABLE IF NOT EXISTS page_index" in sql
    assert "CREATE TABLE IF NOT EXISTS indexed_elements" in sql
    assert "CREATE TABLE IF NOT EXISTS elements" in sql
    assert "CREATE TABLE IF NOT EXISTS locator_variants" in sql
    assert "CREATE TABLE IF NOT EXISTS quality_metrics" in sql
    assert "CREATE TABLE IF NOT EXISTS events" in sql
    assert "CREATE TABLE IF NOT EXISTS healing_events" in sql
    assert "CREATE TABLE IF NOT EXISTS rag_documents" in sql
    assert "idx_page_index_lookup" in sql
    assert "idx_indexed_elements_page" in sql
    assert "idx_rag_documents_scope" in sql
    assert "signature_embedding" not in sql
    assert "embedding vector(" not in sql


def test_safe_uuid_text_rejects_invalid_values() -> None:
    assert PostgresMetadataRepository._safe_uuid_text(None) is None
    assert PostgresMetadataRepository._safe_uuid_text("") is None
    assert PostgresMetadataRepository._safe_uuid_text("not-a-uuid") is None
    assert PostgresMetadataRepository._safe_uuid_text("6f7f8f08-8fde-4f12-9a0f-c5bbd3ed6c9f") == "6f7f8f08-8fde-4f12-9a0f-c5bbd3ed6c9f"
