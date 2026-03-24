[CmdletBinding()]
param(
    [string]$Dsn = $env:XH_PG_DSN,
    [string]$ChromaPath = $(if ($env:XH_CHROMA_PATH) { $env:XH_CHROMA_PATH } else { "artifacts/chroma" }),
    [string]$RagCollection = $(if ($env:XH_CHROMA_RAG_COLLECTION) { $env:XH_CHROMA_RAG_COLLECTION } else { "xh_rag_documents" }),
    [string]$ElementsCollection = $(if ($env:XH_CHROMA_ELEMENTS_COLLECTION) { $env:XH_CHROMA_ELEMENTS_COLLECTION } else { "xh_elements" }),
    [switch]$DataOnly,
    [switch]$SkipPostgres,
    [switch]$SkipChroma
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    $venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return (Resolve-Path $venvPython).Path
    }
    return "python"
}

function Invoke-PsqlSql {
    param(
        [Parameter(Mandatory = $true)][string]$Sql,
        [Parameter(Mandatory = $true)][string]$DsnValue
    )
    & psql $DsnValue -v "ON_ERROR_STOP=1" -c $Sql
    if ($LASTEXITCODE -ne 0) {
        throw "psql command failed."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$python = Get-PythonCommand

if (-not $SkipPostgres) {
    if ([string]::IsNullOrWhiteSpace($Dsn)) {
        throw "XH_PG_DSN is empty. Set env var or pass -Dsn."
    }

    Write-Host "[1/4] Listing current PostgreSQL tables and indexes..."
    Invoke-PsqlSql -DsnValue $Dsn -Sql "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename;"
    Invoke-PsqlSql -DsnValue $Dsn -Sql "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename, indexname;"

    if ($DataOnly) {
        Write-Host "[2/4] Truncating solution tables (data-only reset)..."
        Invoke-PsqlSql -DsnValue $Dsn -Sql "TRUNCATE TABLE indexed_elements, page_index, locator_variants, quality_metrics, healing_events, events, rag_documents, elements RESTART IDENTITY CASCADE;"
    }
    else {
        Write-Host "[2/4] Dropping solution tables..."
        Invoke-PsqlSql -DsnValue $Dsn -Sql "DROP TABLE IF EXISTS indexed_elements, page_index, locator_variants, quality_metrics, healing_events, events, rag_documents, elements CASCADE;"

        Write-Host "[3/4] Recreating PostgreSQL schema from current code (schema_sql)..."
        $schemaSql = & $python -c "from xpath_healer.store.pg_repository import PostgresMetadataRepository as P; print(P.schema_sql())"
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($schemaSql)) {
            throw "Could not load schema SQL from xpath_healer.store.pg_repository.PostgresMetadataRepository.schema_sql()."
        }
        $schemaSql | & psql $Dsn -v "ON_ERROR_STOP=1" -f -
        if ($LASTEXITCODE -ne 0) {
            throw "Schema recreate failed."
        }
    }

    Write-Host "[4/4] PostgreSQL final objects:"
    Invoke-PsqlSql -DsnValue $Dsn -Sql "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename;"
    Invoke-PsqlSql -DsnValue $Dsn -Sql "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename, indexname;"
}

if (-not $SkipChroma) {
    Write-Host "[Chroma] Resetting collections..."
    $env:XH_RESET_CHROMA_PATH = $ChromaPath
    $env:XH_RESET_CHROMA_RAG_COLLECTION = $RagCollection
    $env:XH_RESET_CHROMA_ELEMENTS_COLLECTION = $ElementsCollection

    @'
import os
import sys

try:
    import chromadb
except Exception as exc:
    raise SystemExit(f"chromadb import failed: {exc}")

path = os.environ.get("XH_RESET_CHROMA_PATH", "artifacts/chroma")
rag = os.environ.get("XH_RESET_CHROMA_RAG_COLLECTION", "xh_rag_documents")
elements = os.environ.get("XH_RESET_CHROMA_ELEMENTS_COLLECTION", "xh_elements")

client = chromadb.PersistentClient(path=path)

for name in (rag, elements):
    try:
        client.delete_collection(name=name)
        print(f"deleted: {name}")
    except Exception as exc:
        print(f"skip delete: {name} ({exc})")

client.get_or_create_collection(name=rag, metadata={"hnsw:space": "cosine"})
client.get_or_create_collection(name=elements, metadata={"hnsw:space": "cosine"})
print(f"created: {rag}")
print(f"created: {elements}")
print("collections:", [c.name for c in client.list_collections()])
'@ | & $python -

    if ($LASTEXITCODE -ne 0) {
        throw "Chroma reset failed."
    }
}

Write-Host "Reset completed."
