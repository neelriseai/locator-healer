"""Integration-specific fixtures, artifacts, and logging hooks."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from html import escape
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright

from tests.integration.settings import IntegrationSettings, ensure_artifact_dirs, load_settings
from xpath_healer.core.models import PageIndex
from xpath_healer.store.dual_repository import DualMetadataRepository
from xpath_healer.store.json_repository import JsonMetadataRepository
from xpath_healer.store.pg_repository import PostgresMetadataRepository
from xpath_healer.store.repository import MetadataRepository
from xpath_healer.utils.env import load_env_into_process


# For integration runs, load non-secret defaults from workspace env files.
# Process/user variables still override these values.
load_env_into_process(include_env=True, include_example=True, override=False)


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, default=str))
        fh.write("\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except Exception:
                continue
            if isinstance(raw, dict):
                rows.append(raw)
    return rows


@dataclass
class AsyncRuntime:
    loop: asyncio.AbstractEventLoop

    def run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, minimum: int) -> int:
    value = os.getenv(name)
    if value is None:
        return max(default, minimum)
    try:
        parsed = int(value.strip())
    except Exception:
        return max(default, minimum)
    return max(parsed, minimum)


def _playwright_window_size() -> tuple[int, int]:
    width = _env_int("XH_PLAYWRIGHT_WINDOW_WIDTH", default=1920, minimum=1024)
    height = _env_int("XH_PLAYWRIGHT_WINDOW_HEIGHT", default=1080, minimum=720)
    return width, height


def _resolve_playwright_launch(playwright: Any, settings: IntegrationSettings) -> tuple[Any, dict[str, Any], str]:
    browser = (settings.playwright_browser or "chromium").strip().lower()
    launch_kwargs: dict[str, Any] = {"headless": settings.headless}
    window_width, window_height = _playwright_window_size()
    chromium_window_args = [f"--window-size={window_width},{window_height}"]
    if not settings.headless:
        chromium_window_args.append("--start-maximized")

    if browser in {"chromium", "firefox", "webkit"}:
        browser_type = getattr(playwright, browser, playwright.chromium)
        if settings.playwright_channel:
            launch_kwargs["channel"] = settings.playwright_channel
        if browser == "chromium":
            launch_kwargs["args"] = chromium_window_args
        return browser_type, launch_kwargs, browser

    if browser in {"chrome", "google-chrome"}:
        browser_type = playwright.chromium
        launch_kwargs["channel"] = settings.playwright_channel or "chrome"
        launch_kwargs["args"] = chromium_window_args
        return browser_type, launch_kwargs, "chrome"

    if browser in {"edge", "msedge"}:
        browser_type = playwright.chromium
        launch_kwargs["channel"] = settings.playwright_channel or "msedge"
        launch_kwargs["args"] = chromium_window_args
        return browser_type, launch_kwargs, "msedge"

    browser_type = playwright.chromium
    if settings.playwright_channel:
        launch_kwargs["channel"] = settings.playwright_channel
    launch_kwargs["args"] = chromium_window_args
    return browser_type, launch_kwargs, browser


class LoggedMetadataRepository(MetadataRepository):
    def __init__(
        self,
        backend: MetadataRepository,
        logger: logging.Logger,
        report_jsonl: Path,
    ) -> None:
        self.backend = backend
        self.logger = logger
        self.report_jsonl = report_jsonl
        self.events: list[dict[str, Any]] = []
        backend_events = getattr(backend, "events", None)
        if isinstance(backend_events, list):
            self.events = backend_events

    def _record_db_op(
        self,
        operation: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        backend_name = type(self.backend).__name__
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "record_type": "db_operation",
            "status": status,
            "db_operation": operation,
            "db_backend": backend_name,
            **details,
        }
        self.logger.info(
            "db_operation backend=%s operation=%s status=%s details=%s",
            backend_name,
            operation,
            status,
            details,
        )
        _append_jsonl(self.report_jsonl, payload)

    async def find(self, app_id: str, page_name: str, element_name: str) -> Any:
        try:
            out = await self.backend.find(app_id, page_name, element_name)
            self._record_db_op(
                operation="find",
                status="ok",
                details={
                    "app_id": app_id,
                    "page_name": page_name,
                    "element_name": element_name,
                    "result": "hit" if out else "miss",
                },
            )
            return out
        except Exception as exc:
            self._record_db_op(
                operation="find",
                status="fail",
                details={
                    "app_id": app_id,
                    "page_name": page_name,
                    "element_name": element_name,
                    "error": str(exc),
                },
            )
            raise

    async def upsert(self, meta: Any) -> None:
        try:
            await self.backend.upsert(meta)
            self._record_db_op(
                operation="upsert",
                status="ok",
                details={
                    "app_id": getattr(meta, "app_id", ""),
                    "page_name": getattr(meta, "page_name", ""),
                    "element_name": getattr(meta, "element_name", ""),
                    "field_type": getattr(meta, "field_type", ""),
                    "success_count": getattr(meta, "success_count", None),
                    "fail_count": getattr(meta, "fail_count", None),
                },
            )
        except Exception as exc:
            self._record_db_op(
                operation="upsert",
                status="fail",
                details={
                    "app_id": getattr(meta, "app_id", ""),
                    "page_name": getattr(meta, "page_name", ""),
                    "element_name": getattr(meta, "element_name", ""),
                    "field_type": getattr(meta, "field_type", ""),
                    "error": str(exc),
                },
            )
            raise

    async def find_candidates_by_page(
        self,
        app_id: str,
        page_name: str,
        field_type: str,
        limit: int = 25,
    ) -> list[Any]:
        try:
            out = await self.backend.find_candidates_by_page(app_id, page_name, field_type, limit=limit)
            self._record_db_op(
                operation="find_candidates_by_page",
                status="ok",
                details={
                    "app_id": app_id,
                    "page_name": page_name,
                    "field_type": field_type,
                    "limit": limit,
                    "result_count": len(out),
                },
            )
            return out
        except Exception as exc:
            self._record_db_op(
                operation="find_candidates_by_page",
                status="fail",
                details={
                    "app_id": app_id,
                    "page_name": page_name,
                    "field_type": field_type,
                    "limit": limit,
                    "error": str(exc),
                },
            )
            raise

    async def get_page_index(self, app_id: str, page_name: str) -> PageIndex | None:
        try:
            out = await self.backend.get_page_index(app_id, page_name)
            self._record_db_op(
                operation="get_page_index",
                status="ok",
                details={
                    "app_id": app_id,
                    "page_name": page_name,
                    "result": "hit" if out else "miss",
                },
            )
            return out
        except Exception as exc:
            self._record_db_op(
                operation="get_page_index",
                status="fail",
                details={
                    "app_id": app_id,
                    "page_name": page_name,
                    "error": str(exc),
                },
            )
            raise

    async def upsert_page_index(self, page_index: PageIndex) -> None:
        try:
            await self.backend.upsert_page_index(page_index)
            self._record_db_op(
                operation="upsert_page_index",
                status="ok",
                details={
                    "app_id": page_index.app_id,
                    "page_name": page_index.page_name,
                    "element_count": len(page_index.elements),
                    "dom_hash": page_index.dom_hash[:12],
                },
            )
        except Exception as exc:
            self._record_db_op(
                operation="upsert_page_index",
                status="fail",
                details={
                    "app_id": page_index.app_id,
                    "page_name": page_index.page_name,
                    "error": str(exc),
                },
            )
            raise

    async def log_event(self, event: dict[str, Any]) -> None:
        try:
            await self.backend.log_event(event)
            if not hasattr(self.backend, "events"):
                self.events.append(event)
            self._record_db_op(
                operation="log_event",
                status="ok",
                details={
                    "app_id": event.get("app_id"),
                    "page_name": event.get("page_name"),
                    "element_name": event.get("element_name"),
                    "stage": event.get("stage"),
                },
            )
        except Exception as exc:
            self._record_db_op(
                operation="log_event",
                status="fail",
                details={
                    "app_id": event.get("app_id"),
                    "page_name": event.get("page_name"),
                    "element_name": event.get("element_name"),
                    "stage": event.get("stage"),
                    "error": str(exc),
                },
            )
            raise

    async def close(self) -> None:
        close_method = getattr(self.backend, "close", None)
        if close_method is None:
            return
        maybe = close_method()
        if asyncio.iscoroutine(maybe):
            await maybe


@pytest.fixture(scope="session")
def integration_settings() -> IntegrationSettings:
    settings = load_settings()
    ensure_artifact_dirs(settings)
    return settings


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Any) -> None:
    settings = load_settings()
    ensure_artifact_dirs(settings)
    if not getattr(config.option, "xmlpath", None):
        config.option.xmlpath = str(settings.junit_xml_path)
    if hasattr(config.option, "cucumberjson") and not getattr(config.option, "cucumberjson", None):
        config.option.cucumberjson = str(settings.cucumber_json_path)


@pytest.fixture(scope="session")
def integration_logger(integration_settings: IntegrationSettings) -> logging.Logger:
    logger = logging.getLogger("xpath_healer.integration")
    logger.setLevel(logging.INFO)
    log_file = integration_settings.logs_dir / "integration.log"
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()
    if not any(
        isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


@pytest.fixture(scope="session", autouse=True)
def healing_flow_logger(integration_settings: IntegrationSettings) -> logging.Logger:
    logger = logging.getLogger("xpath_healer")
    logger.setLevel(logging.INFO)
    log_file = integration_settings.logs_dir / "healing-flow.log"
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file:
            logger.removeHandler(handler)
            handler.close()
    if not any(
        isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file
        for handler in logger.handlers
    ):
        handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger


@pytest.fixture(scope="session", autouse=True)
def prepare_artifacts(integration_settings: IntegrationSettings) -> None:
    # Keep only current run artifacts for clear reporting.
    for path in (
        integration_settings.step_report_jsonl,
        integration_settings.healing_calls_jsonl,
        integration_settings.cucumber_json_path,
        integration_settings.junit_xml_path,
        integration_settings.html_report_path,
    ):
        if path.exists():
            path.unlink()
    for directory, pattern in (
        (integration_settings.screenshots_dir, "*.png"),
        (integration_settings.videos_dir, "*.webm"),
    ):
        for file in directory.glob(pattern):
            try:
                file.unlink()
            except Exception:
                pass


@pytest.fixture(scope="session")
def metadata_repository(
    integration_settings: IntegrationSettings,
    integration_logger: logging.Logger,
) -> LoggedMetadataRepository:
    pg_dsn = (os.getenv("XH_PG_DSN") or "").strip()
    json_backend = JsonMetadataRepository(integration_settings.metadata_dir)
    if pg_dsn:
        pg_backend: MetadataRepository = PostgresMetadataRepository(
            dsn=pg_dsn,
            pool_min_size=int((os.getenv("XH_PG_POOL_MIN") or "1").strip()),
            pool_max_size=int((os.getenv("XH_PG_POOL_MAX") or "10").strip()),
            auto_init_schema=_env_bool("XH_PG_AUTO_INIT_SCHEMA", True),
        )
        backend: MetadataRepository = DualMetadataRepository(primary=pg_backend, fallback=json_backend)
        integration_logger.info("metadata_repository backend=DualMetadataRepository(primary=Postgres,fallback=Json)")
    else:
        backend = json_backend
        integration_logger.info("metadata_repository backend=JsonMetadataRepository")

    return LoggedMetadataRepository(
        backend=backend,
        logger=integration_logger,
        report_jsonl=integration_settings.healing_calls_jsonl,
    )


@pytest.fixture(scope="session", autouse=True)
def metadata_repository_lifecycle(
    metadata_repository: LoggedMetadataRepository,
    runtime: AsyncRuntime,
) -> Any:
    yield
    try:
        runtime.run(metadata_repository.close())
    except Exception:
        # Repository close is best-effort in integration teardown.
        pass


@pytest.fixture(scope="session")
def runtime() -> Any:
    loop = asyncio.new_event_loop()
    try:
        yield AsyncRuntime(loop=loop)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


@pytest.fixture
def page(
    runtime: AsyncRuntime,
    request: Any,
    integration_settings: IntegrationSettings,
    integration_logger: logging.Logger,
) -> Any:
    try:
        playwright = runtime.run(async_playwright().start())
    except Exception as exc:
        pytest.skip(f"Playwright runtime unavailable: {exc}")
    browser_type, launch_kwargs, browser_name = _resolve_playwright_launch(playwright, integration_settings)

    try:
        browser = runtime.run(browser_type.launch(**launch_kwargs))
    except Exception as exc:
        runtime.run(playwright.stop())
        pytest.skip(f"Playwright browser unavailable: {exc}")

    window_width, window_height = _playwright_window_size()
    context_kwargs: dict[str, Any] = {
        # Force a stable large viewport regardless of headed/headless and OS window manager behavior.
        "viewport": {"width": window_width, "height": window_height},
        "screen": {"width": window_width, "height": window_height},
    }
    if integration_settings.video_each_test:
        context_kwargs["record_video_dir"] = str(integration_settings.videos_dir)
        context_kwargs["record_video_size"] = {
            "width": integration_settings.video_width,
            "height": integration_settings.video_height,
        }
    context = runtime.run(browser.new_context(**context_kwargs))
    p = runtime.run(context.new_page())
    p.set_default_timeout(20_000)
    integration_logger.info(
        "browser_started framework=playwright browser=%s channel=%s headless=%s viewport=%sx%s",
        browser_name,
        launch_kwargs.get("channel", ""),
        integration_settings.headless,
        window_width,
        window_height,
    )
    try:
        yield p
    finally:
        test_name = _slug(request.node.name)
        video_path: str | None = None
        # Always capture final screenshot for every test.
        if integration_settings.screenshot_each_test:
            final_path = integration_settings.screenshots_dir / f"{test_name}__final.png"
            try:
                runtime.run(p.screenshot(path=str(final_path), full_page=True))
                integration_logger.info("screenshot_saved test=%s path=%s", test_name, final_path)
            except Exception as exc:
                integration_logger.error("screenshot_failed test=%s error=%s", test_name, exc)

        rep_call = getattr(request.node, "rep_call", None)
        if rep_call and rep_call.failed and integration_settings.screenshot_on_failure:
            fail_path = integration_settings.screenshots_dir / f"{test_name}__failed.png"
            try:
                runtime.run(p.screenshot(path=str(fail_path), full_page=True))
                integration_logger.info("failure_screenshot_saved test=%s path=%s", test_name, fail_path)
            except Exception as exc:
                integration_logger.error("failure_screenshot_failed test=%s error=%s", test_name, exc)

        runtime.run(context.close())
        if integration_settings.video_each_test and getattr(p, "video", None):
            try:
                video_path = runtime.run(p.video.path())
            except Exception:
                pass
        if video_path:
            named_video = integration_settings.videos_dir / f"{test_name}.webm"
            try:
                if named_video.exists():
                    named_video.unlink()
                Path(video_path).replace(named_video)
                integration_logger.info("video_saved test=%s path=%s", test_name, named_video)
            except Exception as exc:
                integration_logger.error("video_rename_failed test=%s source=%s error=%s", test_name, video_path, exc)
        runtime.run(browser.close())
        runtime.run(playwright.stop())


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.rep_call = report


def pytest_bdd_before_scenario(request: Any, feature: Any, scenario: Any) -> None:
    request.node._bdd_step_index = 0


def pytest_bdd_after_step(request: Any, feature: Any, scenario: Any, step: Any, step_func: Any, step_func_args: dict[str, Any]) -> None:
    settings: IntegrationSettings = request.getfixturevalue("integration_settings")
    logger: logging.Logger = request.getfixturevalue("integration_logger")
    runtime: AsyncRuntime = request.getfixturevalue("runtime")
    page = None
    try:
        page = request.getfixturevalue("page")
    except Exception as exc:
        logger.warning("step_screenshot_skipped test=%s reason=page_unavailable error=%s", request.node.name, exc)

    request.node._bdd_step_index = int(getattr(request.node, "_bdd_step_index", 0)) + 1
    step_idx = request.node._bdd_step_index
    test_name = _slug(request.node.name)
    step_name = _slug(getattr(step, "name", "step"))
    step_keyword = getattr(step, "keyword", "")
    screenshot_path = None
    if settings.screenshot_each_step and page is not None:
        screenshot_path = settings.screenshots_dir / f"{test_name}__step{step_idx:02d}__{step_name}.png"
        try:
            runtime.run(page.screenshot(path=str(screenshot_path), full_page=True))
            logger.info(
                "step_screenshot_saved test=%s step=%s keyword=%s path=%s",
                test_name,
                step_name,
                step_keyword.strip(),
                screenshot_path,
            )
        except Exception as exc:
            logger.error("step_screenshot_failed test=%s step=%s error=%s", test_name, step_name, exc)
            screenshot_path = None

    _append_jsonl(
        settings.step_report_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "test": request.node.name,
            "scenario": getattr(scenario, "name", request.node.name),
            "step_index": step_idx,
            "step_keyword": step_keyword.strip(),
            "step_name": getattr(step, "name", ""),
            "status": "passed",
            "screenshot": str(screenshot_path) if screenshot_path else None,
        },
    )


def pytest_bdd_step_error(
    request: Any,
    feature: Any,
    scenario: Any,
    step: Any,
    step_func: Any,
    step_func_args: dict[str, Any],
    exception: Exception,
) -> None:
    settings: IntegrationSettings = request.getfixturevalue("integration_settings")
    logger: logging.Logger = request.getfixturevalue("integration_logger")
    runtime: AsyncRuntime = request.getfixturevalue("runtime")
    page = None
    try:
        page = request.getfixturevalue("page")
    except Exception as exc:
        logger.warning("step_error_screenshot_skipped test=%s reason=page_unavailable error=%s", request.node.name, exc)

    request.node._bdd_step_index = int(getattr(request.node, "_bdd_step_index", 0)) + 1
    step_idx = request.node._bdd_step_index
    test_name = _slug(request.node.name)
    step_name = _slug(getattr(step, "name", "step"))
    step_keyword = getattr(step, "keyword", "")
    screenshot_path = None
    if page is not None:
        screenshot_path = settings.screenshots_dir / f"{test_name}__step{step_idx:02d}__{step_name}__error.png"
        try:
            runtime.run(page.screenshot(path=str(screenshot_path), full_page=True))
            logger.error(
                "step_error_screenshot_saved test=%s step=%s keyword=%s path=%s error=%s",
                test_name,
                step_name,
                step_keyword.strip(),
                screenshot_path,
                exception,
            )
        except Exception as exc:
            logger.error("step_error_screenshot_failed test=%s step=%s error=%s", test_name, step_name, exc)
            screenshot_path = None

    _append_jsonl(
        settings.step_report_jsonl,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "test": request.node.name,
            "scenario": getattr(scenario, "name", request.node.name),
            "step_index": step_idx,
            "step_keyword": step_keyword.strip(),
            "step_name": getattr(step, "name", ""),
            "status": "failed",
            "error": str(exception),
            "screenshot": str(screenshot_path) if screenshot_path else None,
        },
    )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    settings = load_settings()
    ensure_artifact_dirs(settings)
    steps = _load_jsonl(settings.step_report_jsonl)
    all_heals = _load_jsonl(settings.healing_calls_jsonl)
    db_ops = [row for row in all_heals if row.get("record_type") == "db_operation"]
    heals = [row for row in all_heals if row.get("record_type") != "db_operation"]

    pass_count = len([s for s in steps if s.get("status") == "passed"])
    fail_count = len([s for s in steps if s.get("status") == "failed"])
    db_ok = len([row for row in db_ops if row.get("status") == "ok"])
    db_fail = len([row for row in db_ops if row.get("status") == "fail"])
    summary = (
        f"<p>Step events: passed={pass_count}, failed={fail_count}. "
        f"DB ops: ok={db_ok}, fail={db_fail}. "
        f"Session exitstatus={exitstatus}</p>"
    )

    step_rows = []
    for row in steps:
        screenshot = row.get("screenshot")
        screenshot_cell = ""
        if screenshot:
            spath = Path(str(screenshot))
            try:
                if spath.parts and spath.parts[0] == "artifacts":
                    rel = Path("..") / spath.relative_to("artifacts")
                else:
                    rel = spath
            except Exception:
                rel = spath
            screenshot_cell = f'<a href="{escape(str(rel).replace("\\", "/"))}">view</a>'
        step_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('test', '')))}</td>"
            f"<td>{escape(str(row.get('scenario', '')))}</td>"
            f"<td>{escape(str(row.get('step_index', '')))}</td>"
            f"<td>{escape(str(row.get('step_keyword', '')))}</td>"
            f"<td>{escape(str(row.get('step_name', '')))}</td>"
            f"<td>{escape(str(row.get('status', '')))}</td>"
            f"<td>{screenshot_cell}</td>"
            "</tr>"
        )

    heal_rows = []
    for row in heals:
        selected_kind = row.get("selected_locator_kind", row.get("healed_locator_kind", ""))
        selected_value = row.get("selected_locator_value", row.get("healed_locator_value", ""))
        selected_locator = f"{selected_kind}:{selected_value}" if selected_kind or selected_value else ""
        healed_xpath = row.get("healed_xpath", row.get("robust_xpath", row.get("live_xpath", row.get("healed_locator_value", ""))))
        healed_css = row.get("healed_css", row.get("robust_css", row.get("live_css", "")))
        heal_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('page_name', '')))}</td>"
            f"<td>{escape(str(row.get('element_name', '')))}</td>"
            f"<td>{escape(str(row.get('status', '')))}</td>"
            f"<td>{escape(str(row.get('strategy_id', '')))}</td>"
            f"<td><code>{escape(str(selected_locator))}</code></td>"
            f"<td><code>{escape(str(row.get('fallback_xpath', '')))}</code></td>"
            f"<td><code>{escape(str(healed_xpath))}</code></td>"
            f"<td>{escape(str(row.get('healed_xpath_source', '')))}</td>"
            f"<td><code>{escape(str(healed_css))}</code></td>"
            f"<td>{escape(str(row.get('healed_css_source', '')))}</td>"
            f"<td>{escape(str(row.get('uniqueness_score', '')))}</td>"
            f"<td>{escape(str(row.get('stability_score', '')))}</td>"
            f"<td>{escape(str(row.get('similarity_score', '')))}</td>"
            f"<td>{escape(str(row.get('overall_score', '')))}</td>"
            "</tr>"
        )

    db_rows = []
    for row in db_ops:
        db_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('timestamp', '')))}</td>"
            f"<td>{escape(str(row.get('db_backend', '')))}</td>"
            f"<td>{escape(str(row.get('db_operation', '')))}</td>"
            f"<td>{escape(str(row.get('status', '')))}</td>"
            f"<td>{escape(str(row.get('app_id', '')))}</td>"
            f"<td>{escape(str(row.get('page_name', '')))}</td>"
            f"<td>{escape(str(row.get('element_name', '')))}</td>"
            f"<td>{escape(str(row.get('result', row.get('result_count', row.get('stage', '')))))}</td>"
            f"<td><code>{escape(str(row.get('error', '')))}</code></td>"
            "</tr>"
        )

    video_links = []
    for video in sorted(settings.videos_dir.glob("*.webm")):
        rel = Path("..") / Path("videos") / video.name
        video_links.append(f'<li><a href="{escape(str(rel).replace("\\", "/"))}">{escape(video.name)}</a></li>')

    metadata_links = []
    if settings.metadata_dir.exists():
        for meta in sorted(settings.metadata_dir.rglob("*.json")):
            rel = Path("..") / meta.relative_to(settings.artifacts_root)
            metadata_links.append(f'<li><a href="{escape(str(rel).replace("\\", "/"))}">{escape(meta.name)}</a></li>')

    report_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>XPath Healer Integration Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 16px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 18px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; font-size: 12px; }}
    th {{ background: #f3f3f3; text-align: left; }}
    code {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>XPath Healer Integration Report</h1>
  {summary}
  <p>
    <a href="integration-junit.xml">JUnit XML</a> |
    <a href="cucumber.json">Cucumber JSON</a> |
    <a href="steps.jsonl">Step JSONL</a> |
    <a href="healing-calls.jsonl">Healing Calls JSONL</a> |
    <a href="../logs/integration.log">Integration Log</a> |
    <a href="../logs/healing-flow.log">Healing Flow Log</a>
  </p>
  <h2>Step Details</h2>
  <table>
    <thead>
      <tr><th>Test</th><th>Scenario</th><th>#</th><th>Keyword</th><th>Step</th><th>Status</th><th>Screenshot</th></tr>
    </thead>
    <tbody>
      {''.join(step_rows)}
    </tbody>
  </table>
  <h2>DB Operations</h2>
  <table>
    <thead>
      <tr><th>Timestamp</th><th>Backend</th><th>Operation</th><th>Status</th><th>App</th><th>Page</th><th>Element</th><th>Result</th><th>Error</th></tr>
    </thead>
    <tbody>
      {''.join(db_rows)}
    </tbody>
  </table>
  <h2>Healing Calls</h2>
  <table>
    <thead>
      <tr><th>Page</th><th>Element</th><th>Status</th><th>Strategy</th><th>Selected Locator</th><th>Fallback XPath</th><th>Healed XPath</th><th>XPath Source</th><th>Healed CSS</th><th>CSS Source</th><th>Uniqueness</th><th>Stability</th><th>Similarity</th><th>Overall</th></tr>
    </thead>
    <tbody>
      {''.join(heal_rows)}
    </tbody>
  </table>
  <h2>Videos</h2>
  <ul>{''.join(video_links)}</ul>
  <h2>Metadata Files</h2>
  <ul>{''.join(metadata_links)}</ul>
</body>
</html>
"""

    report_path = settings.html_report_path
    report_path.write_text(report_html, encoding="utf-8")
