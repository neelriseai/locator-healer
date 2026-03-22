"""Integration test configuration loader."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from xpath_healer.utils.env import load_env_into_process


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class IntegrationSettings:
    base_url: str
    playwright_browser: str
    playwright_channel: str | None
    selenium_browser: str
    selenium_binary_path: str | None
    headless: bool
    artifacts_root: Path
    reports_dir: Path
    logs_dir: Path
    screenshots_dir: Path
    videos_dir: Path
    metadata_dir: Path
    junit_xml_path: Path
    cucumber_json_path: Path
    step_report_jsonl: Path
    healing_calls_jsonl: Path
    html_report_path: Path
    screenshot_each_test: bool
    screenshot_on_failure: bool
    screenshot_each_step: bool
    video_each_test: bool
    video_width: int
    video_height: int


def load_settings(config_path: Path | None = None) -> IntegrationSettings:
    load_env_into_process(include_env=True, include_example=True, override=False)
    config_path = config_path or Path(__file__).with_name("config.json")
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    base_url = os.getenv("XH_BASE_URL", str(raw.get("base_url") or "")).rstrip("/")
    browser_raw = raw.get("browser") or {}
    artifacts_raw = raw.get("artifacts") or {}
    capture_raw = raw.get("capture") or {}

    legacy_browser = os.getenv("XH_BROWSER_ENGINE", str(browser_raw.get("engine") or "chromium")).strip().lower()
    playwright_browser_default = str(browser_raw.get("playwright_browser") or legacy_browser or "chromium").strip().lower()
    playwright_browser = os.getenv("XH_PLAYWRIGHT_BROWSER", playwright_browser_default).strip().lower()
    playwright_channel_default = browser_raw.get("playwright_channel", browser_raw.get("channel"))
    playwright_channel = os.getenv("XH_PLAYWRIGHT_CHANNEL", os.getenv("XH_BROWSER_CHANNEL", playwright_channel_default))
    selenium_browser_default = str(browser_raw.get("selenium_browser") or "chrome").strip().lower()
    selenium_browser = os.getenv("XH_SELENIUM_BROWSER", selenium_browser_default).strip().lower()
    selenium_binary_path = os.getenv("XH_SELENIUM_BINARY", browser_raw.get("selenium_binary"))
    headless = _env_bool("XH_HEADLESS", bool(browser_raw.get("headless", True)))

    root_dir = Path(os.getenv("XH_ARTIFACTS_ROOT", str(artifacts_raw.get("root_dir") or "artifacts")))
    reports_dir = Path(os.getenv("XH_REPORTS_DIR", str(artifacts_raw.get("reports_dir") or root_dir / "reports")))
    logs_dir = Path(os.getenv("XH_LOGS_DIR", str(artifacts_raw.get("logs_dir") or root_dir / "logs")))
    screenshots_dir = Path(
        os.getenv("XH_SCREENSHOTS_DIR", str(artifacts_raw.get("screenshots_dir") or root_dir / "screenshots"))
    )
    videos_dir = Path(os.getenv("XH_VIDEOS_DIR", str(artifacts_raw.get("videos_dir") or root_dir / "videos")))
    metadata_dir = Path(os.getenv("XH_METADATA_DIR", str(artifacts_raw.get("metadata_dir") or root_dir / "metadata")))
    junit_xml_path = Path(
        os.getenv("XH_JUNIT_XML", str(artifacts_raw.get("junit_xml") or reports_dir / "integration-junit.xml"))
    )
    cucumber_json_path = Path(
        os.getenv("XH_CUCUMBER_JSON", str(artifacts_raw.get("cucumber_json") or reports_dir / "cucumber.json"))
    )
    step_report_jsonl = Path(
        os.getenv("XH_STEP_REPORT", str(artifacts_raw.get("step_report_jsonl") or reports_dir / "steps.jsonl"))
    )
    healing_calls_jsonl = Path(
        os.getenv("XH_HEALING_CALLS_REPORT", str(artifacts_raw.get("healing_calls_jsonl") or reports_dir / "healing-calls.jsonl"))
    )
    html_report_path = Path(
        os.getenv("XH_HTML_REPORT", str(artifacts_raw.get("html_report") or reports_dir / "integration-report.html"))
    )

    screenshot_each_test = _env_bool(
        "XH_SCREENSHOT_EACH_TEST",
        bool(capture_raw.get("screenshot_each_test", True)),
    )
    screenshot_on_failure = _env_bool(
        "XH_SCREENSHOT_ON_FAILURE",
        bool(capture_raw.get("screenshot_on_failure", True)),
    )
    screenshot_each_step = _env_bool(
        "XH_SCREENSHOT_EACH_STEP",
        bool(capture_raw.get("screenshot_each_step", True)),
    )
    video_each_test = _env_bool(
        "XH_VIDEO_EACH_TEST",
        bool(capture_raw.get("video_each_test", True)),
    )
    video_width = int(os.getenv("XH_VIDEO_WIDTH", str(capture_raw.get("video_width", 640))))
    video_height = int(os.getenv("XH_VIDEO_HEIGHT", str(capture_raw.get("video_height", 360))))

    return IntegrationSettings(
        base_url=base_url,
        playwright_browser=playwright_browser,
        playwright_channel=str(playwright_channel).strip() if playwright_channel else None,
        selenium_browser=selenium_browser,
        selenium_binary_path=str(selenium_binary_path).strip() if selenium_binary_path else None,
        headless=headless,
        artifacts_root=root_dir,
        reports_dir=reports_dir,
        logs_dir=logs_dir,
        screenshots_dir=screenshots_dir,
        videos_dir=videos_dir,
        metadata_dir=metadata_dir,
        junit_xml_path=junit_xml_path,
        cucumber_json_path=cucumber_json_path,
        step_report_jsonl=step_report_jsonl,
        healing_calls_jsonl=healing_calls_jsonl,
        html_report_path=html_report_path,
        screenshot_each_test=screenshot_each_test,
        screenshot_on_failure=screenshot_on_failure,
        screenshot_each_step=screenshot_each_step,
        video_each_test=video_each_test,
        video_width=video_width,
        video_height=video_height,
    )


def ensure_artifact_dirs(settings: IntegrationSettings) -> None:
    settings.artifacts_root.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    settings.metadata_dir.mkdir(parents=True, exist_ok=True)
