import json
import os
from pathlib import Path

from tests.integration.settings import load_settings


def test_load_settings_supports_framework_specific_browser_options() -> None:
    temp_dir = Path("artifacts") / "test-temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "integration-settings-test.json"
    env_names = [
        "XH_BROWSER_ENGINE",
        "XH_BROWSER_CHANNEL",
        "XH_PLAYWRIGHT_BROWSER",
        "XH_PLAYWRIGHT_CHANNEL",
        "XH_SELENIUM_BROWSER",
        "XH_SELENIUM_BINARY",
    ]
    saved_env = {name: os.environ.get(name) for name in env_names}
    try:
        for name in env_names:
            os.environ.pop(name, None)
        config_path.write_text(
            json.dumps(
                {
                    "base_url": "https://example.test",
                    "browser": {
                        "engine": "chromium",
                        "playwright_browser": "chrome",
                        "playwright_channel": "chrome-beta",
                        "selenium_browser": "firefox",
                        "selenium_binary": "/tmp/firefox-bin",
                        "headless": True,
                    },
                    "artifacts": {},
                    "capture": {},
                }
            ),
            encoding="utf-8",
        )

        settings = load_settings(config_path=config_path)

        assert settings.playwright_browser == "chrome"
        assert settings.playwright_channel == "chrome-beta"
        assert settings.selenium_browser == "firefox"
        assert settings.selenium_binary_path == "/tmp/firefox-bin"
    finally:
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if config_path.exists():
            config_path.unlink()
