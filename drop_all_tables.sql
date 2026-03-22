-- Delete all rows from core tables used by xpath-healer (preserve schemas)
BEGIN;
DELETE FROM indexed_elements;
DELETE FROM page_index;
DELETE FROM locator_variants;
DELETE FROM quality_metrics;
DELETE FROM healing_events;
DELETE FROM events;
DELETE FROM rag_documents;
DELETE FROM elements;
COMMIT;
-- Add any other tables you need to clear
