"""Configuration for XPath healer."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

from xpath_healer.utils.text import coerce_bool


DEFAULT_ATTRIBUTE_PRIORITY = [
    "data-testid",
    "aria-label",
    "name",
    "formcontrolname",
    "placeholder",
    "role",
    "href",
    "col-id",
    "aria-colindex",
    "class",
]


@dataclass(slots=True)
class ValidatorGeometryConfig:
    enabled: bool = True
    tolerance_px: float = 8.0


@dataclass(slots=True)
class ValidatorAxisConfig:
    enabled: bool = True


@dataclass(slots=True)
class ValidatorConfig:
    require_visible: bool = True
    require_enabled_for_interactives: bool = True
    strict_single_match: bool = True
    geometry: ValidatorGeometryConfig = field(default_factory=ValidatorGeometryConfig)
    axis: ValidatorAxisConfig = field(default_factory=ValidatorAxisConfig)


@dataclass(slots=True)
class DomSnapshotConfig:
    cache_ttl_sec: int = 30


@dataclass(slots=True)
class StoreConfig:
    enabled: bool = True
    persist_events: bool = True


@dataclass(slots=True)
class RagConfig:
    enabled: bool = False
    top_k: int = 5


@dataclass(slots=True)
class PromptConfig:
    graph_deep_default: bool = False
    graph_deep_retry_enabled: bool = True
    graph_deep_retry_max: int = 1


@dataclass(slots=True)
class LlmConfig:
    min_confidence_for_accept: float = 0.65


@dataclass(slots=True)
class StageConfig:
    profile: str = "full"
    fallback: bool = True
    metadata: bool = True
    rules: bool = True
    fingerprint: bool = True
    # Phase 4c — deterministic free replay of prior step successes.
    # Runs between fallback and metadata so high-precision (workflow +
    # step + outcome) hits short-circuit the rest of the cascade.
    workflow_replay: bool = True
    page_index: bool = True
    signature: bool = True
    option_fingerprint: bool = True
    dom_mining: bool = True
    defaults: bool = True
    position: bool = True
    mcp_explore: bool = True
    rag: bool = True
    # Phase 4c — agent-driven workflow rewrite proposals. Off by
    # default because it costs LLM tokens. Outer agents that want
    # skip/abort proposals when the locator cascade fails opt in.
    workflow_rewrite: bool = False


@dataclass(slots=True)
class FingerprintConfig:
    enabled: bool = True
    min_score: float = 0.75
    accept_score: float = 0.90
    candidate_limit: int = 25


@dataclass(slots=True)
class RetryConfig:
    enabled: bool = True
    max_attempts: int = 2
    delay_ms: int = 30
    retry_reason_codes: list[str] = field(default_factory=lambda: ["locator_error", "locator_timeout", "stale_element", "not_visible"])


@dataclass(slots=True)
class WorkflowHistoryConfig:
    """Phase 4b — workflow run history persistence.

    ``enabled=False`` opts out entirely (no repo is constructed, no
    recording happens). Useful for sensitive workflows where even
    hashed page signatures shouldn't be persisted.

    Backend selection precedence: ``pg_dsn`` (Phase 5) → ``json_dir``
    (Phase 4b) → in-memory.
    """

    enabled: bool = True
    pg_dsn: str = ""
    pg_auto_init_schema: bool = False
    # ``""`` means in-memory only (no file persistence).
    json_dir: str = "artifacts/workflow_runs"
    max_steps_per_workflow: int = 50


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(slots=True)
class AdapterConfig:
    name: str = "playwright_python"


@dataclass(slots=True)
class HealerConfig:
    adapter: AdapterConfig = field(default_factory=AdapterConfig)
    attribute_priority: list[str] = field(default_factory=lambda: list(DEFAULT_ATTRIBUTE_PRIORITY))
    similarity_threshold: float = 0.72
    allow_position_fallback: bool = False
    validator: ValidatorConfig = field(default_factory=ValidatorConfig)
    dom: DomSnapshotConfig = field(default_factory=DomSnapshotConfig)
    store: StoreConfig = field(default_factory=StoreConfig)
    rag: RagConfig = field(default_factory=RagConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    stages: StageConfig = field(default_factory=StageConfig)
    fingerprint: FingerprintConfig = field(default_factory=FingerprintConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    workflow_history: WorkflowHistoryConfig = field(default_factory=WorkflowHistoryConfig)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_env(cls, prefix: str = "XH_") -> HealerConfig:
        cfg = cls()

        adapter_name = os.getenv(f"{prefix}ADAPTER")
        if adapter_name:
            cfg.adapter.name = adapter_name.strip()

        attr_priority = os.getenv(f"{prefix}ATTRIBUTE_PRIORITY")
        if attr_priority:
            cfg.attribute_priority = [token.strip() for token in attr_priority.split(",") if token.strip()]

        similarity_threshold = os.getenv(f"{prefix}SIMILARITY_THRESHOLD")
        if similarity_threshold:
            cfg.similarity_threshold = float(similarity_threshold)

        allow_position = os.getenv(f"{prefix}ALLOW_POSITION_FALLBACK")
        if allow_position is not None:
            cfg.allow_position_fallback = coerce_bool(allow_position, cfg.allow_position_fallback)

        cfg.validator.require_visible = coerce_bool(
            os.getenv(f"{prefix}VALIDATOR_REQUIRE_VISIBLE"),
            cfg.validator.require_visible,
        )
        cfg.validator.require_enabled_for_interactives = coerce_bool(
            os.getenv(f"{prefix}VALIDATOR_REQUIRE_ENABLED"),
            cfg.validator.require_enabled_for_interactives,
        )
        cfg.validator.strict_single_match = coerce_bool(
            os.getenv(f"{prefix}VALIDATOR_STRICT_SINGLE_MATCH"),
            cfg.validator.strict_single_match,
        )
        cfg.validator.geometry.enabled = coerce_bool(
            os.getenv(f"{prefix}VALIDATOR_GEOMETRY_ENABLED"),
            cfg.validator.geometry.enabled,
        )
        tolerance = os.getenv(f"{prefix}VALIDATOR_GEOMETRY_TOLERANCE")
        if tolerance:
            cfg.validator.geometry.tolerance_px = float(tolerance)

        cfg.validator.axis.enabled = coerce_bool(
            os.getenv(f"{prefix}VALIDATOR_AXIS_ENABLED"),
            cfg.validator.axis.enabled,
        )

        cache_ttl = os.getenv(f"{prefix}DOM_CACHE_TTL_SEC")
        if cache_ttl:
            cfg.dom.cache_ttl_sec = int(cache_ttl)

        cfg.store.enabled = coerce_bool(os.getenv(f"{prefix}STORE_ENABLED"), cfg.store.enabled)
        cfg.store.persist_events = coerce_bool(os.getenv(f"{prefix}STORE_PERSIST_EVENTS"), cfg.store.persist_events)

        cfg.rag.enabled = coerce_bool(os.getenv(f"{prefix}RAG_ENABLED"), cfg.rag.enabled)
        rag_top_k = os.getenv(f"{prefix}RAG_TOP_K")
        if rag_top_k:
            cfg.rag.top_k = int(rag_top_k)

        cfg.prompt.graph_deep_default = coerce_bool(
            os.getenv(f"{prefix}PROMPT_GRAPH_DEEP_DEFAULT"),
            cfg.prompt.graph_deep_default,
        )
        cfg.prompt.graph_deep_retry_enabled = coerce_bool(
            os.getenv(f"{prefix}PROMPT_GRAPH_DEEP_RETRY_ENABLED"),
            cfg.prompt.graph_deep_retry_enabled,
        )
        graph_deep_retry_max = os.getenv(f"{prefix}PROMPT_GRAPH_DEEP_RETRY_MAX")
        if graph_deep_retry_max:
            cfg.prompt.graph_deep_retry_max = max(0, int(graph_deep_retry_max))

        min_conf = os.getenv(f"{prefix}LLM_MIN_CONFIDENCE_FOR_ACCEPT")
        if min_conf:
            cfg.llm.min_confidence_for_accept = min(max(float(min_conf), 0.0), 1.0)

        stage_profile = (os.getenv(f"{prefix}STAGE_PROFILE") or cfg.stages.profile).strip().casefold()
        if stage_profile:
            cfg.stages.profile = stage_profile
        if cfg.stages.profile == "llm_only":
            cfg.stages.fallback = False
            cfg.stages.workflow_replay = False
            cfg.stages.metadata = False
            cfg.stages.rules = False
            cfg.stages.fingerprint = False
            cfg.stages.page_index = False
            cfg.stages.signature = False
            cfg.stages.option_fingerprint = False
            cfg.stages.dom_mining = False
            cfg.stages.defaults = False
            cfg.stages.position = False
            cfg.stages.mcp_explore = False
            cfg.stages.workflow_rewrite = False
            cfg.stages.rag = True

        cfg.stages.fallback = coerce_bool(os.getenv(f"{prefix}STAGE_FALLBACK_ENABLED"), cfg.stages.fallback)
        cfg.stages.workflow_replay = coerce_bool(
            os.getenv(f"{prefix}STAGE_WORKFLOW_REPLAY_ENABLED"), cfg.stages.workflow_replay
        )
        cfg.stages.metadata = coerce_bool(os.getenv(f"{prefix}STAGE_METADATA_ENABLED"), cfg.stages.metadata)
        cfg.stages.rules = coerce_bool(os.getenv(f"{prefix}STAGE_RULES_ENABLED"), cfg.stages.rules)
        cfg.stages.fingerprint = coerce_bool(os.getenv(f"{prefix}STAGE_FINGERPRINT_ENABLED"), cfg.stages.fingerprint)
        cfg.stages.page_index = coerce_bool(os.getenv(f"{prefix}STAGE_PAGE_INDEX_ENABLED"), cfg.stages.page_index)
        cfg.stages.signature = coerce_bool(os.getenv(f"{prefix}STAGE_SIGNATURE_ENABLED"), cfg.stages.signature)
        cfg.stages.option_fingerprint = coerce_bool(
            os.getenv(f"{prefix}STAGE_OPTION_FINGERPRINT_ENABLED"), cfg.stages.option_fingerprint
        )
        cfg.stages.dom_mining = coerce_bool(os.getenv(f"{prefix}STAGE_DOM_MINING_ENABLED"), cfg.stages.dom_mining)
        cfg.stages.defaults = coerce_bool(os.getenv(f"{prefix}STAGE_DEFAULTS_ENABLED"), cfg.stages.defaults)
        cfg.stages.position = coerce_bool(os.getenv(f"{prefix}STAGE_POSITION_ENABLED"), cfg.stages.position)
        cfg.stages.mcp_explore = coerce_bool(
            os.getenv(f"{prefix}STAGE_MCP_EXPLORE_ENABLED"), cfg.stages.mcp_explore
        )
        cfg.stages.workflow_rewrite = coerce_bool(
            os.getenv(f"{prefix}STAGE_WORKFLOW_REWRITE_ENABLED"), cfg.stages.workflow_rewrite
        )
        cfg.stages.rag = coerce_bool(os.getenv(f"{prefix}STAGE_RAG_ENABLED"), cfg.stages.rag)

        cfg.fingerprint.enabled = coerce_bool(os.getenv(f"{prefix}FINGERPRINT_ENABLED"), cfg.fingerprint.enabled)
        fp_min_score = os.getenv(f"{prefix}FINGERPRINT_MIN_SCORE")
        if fp_min_score:
            cfg.fingerprint.min_score = max(0.0, min(1.0, float(fp_min_score)))
        fp_accept_score = os.getenv(f"{prefix}FINGERPRINT_ACCEPT_SCORE")
        if fp_accept_score:
            cfg.fingerprint.accept_score = max(0.0, min(1.0, float(fp_accept_score)))
        fp_candidate_limit = os.getenv(f"{prefix}FINGERPRINT_CANDIDATE_LIMIT")
        if fp_candidate_limit:
            cfg.fingerprint.candidate_limit = max(1, int(fp_candidate_limit))

        cfg.retry.enabled = coerce_bool(os.getenv(f"{prefix}RETRY_ENABLED"), cfg.retry.enabled)
        retry_max_attempts = os.getenv(f"{prefix}RETRY_MAX_ATTEMPTS")
        if retry_max_attempts:
            cfg.retry.max_attempts = max(1, int(retry_max_attempts))
        retry_delay_ms = os.getenv(f"{prefix}RETRY_DELAY_MS")
        if retry_delay_ms:
            cfg.retry.delay_ms = max(0, int(retry_delay_ms))
        retry_reasons = os.getenv(f"{prefix}RETRY_REASON_CODES")
        if retry_reasons:
            cfg.retry.retry_reason_codes = [
                token.strip().casefold()
                for token in retry_reasons.split(",")
                if token.strip()
            ]

        level = os.getenv(f"{prefix}LOG_LEVEL")
        if level:
            cfg.logging.level = level.upper().strip()

        cfg.workflow_history.enabled = coerce_bool(
            os.getenv(f"{prefix}WORKFLOW_HISTORY_ENABLED"), cfg.workflow_history.enabled
        )
        wf_pg_dsn = os.getenv(f"{prefix}WORKFLOW_HISTORY_PG_DSN")
        if wf_pg_dsn is not None:
            cfg.workflow_history.pg_dsn = wf_pg_dsn.strip()
        cfg.workflow_history.pg_auto_init_schema = coerce_bool(
            os.getenv(f"{prefix}WORKFLOW_HISTORY_PG_AUTO_INIT_SCHEMA"),
            cfg.workflow_history.pg_auto_init_schema,
        )
        wf_json_dir = os.getenv(f"{prefix}WORKFLOW_HISTORY_JSON_DIR")
        if wf_json_dir is not None:
            cfg.workflow_history.json_dir = wf_json_dir.strip()
        wf_max = os.getenv(f"{prefix}WORKFLOW_HISTORY_MAX_STEPS_PER_WORKFLOW")
        if wf_max:
            try:
                cfg.workflow_history.max_steps_per_workflow = max(1, int(wf_max))
            except ValueError:
                pass

        return cfg
