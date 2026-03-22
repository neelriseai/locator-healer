import pytest

from xpath_healer.dom.snapshot import DomSnapshotter


class StubAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def capture_page_html(self, page):  # type: ignore[no-untyped-def]
        self.calls += 1
        return f"<html><body>{page.current_url}</body></html>"


class StubPage:
    def __init__(self, url: str) -> None:
        self.current_url = url


@pytest.mark.asyncio
async def test_snapshot_cache_invalidates_when_page_url_changes() -> None:
    adapter = StubAdapter()
    snapshotter = DomSnapshotter(adapter=adapter, cache_ttl_sec=30)
    page = StubPage("https://example.test/checkbox")

    first = await snapshotter.capture(page)
    second = await snapshotter.capture(page)
    page.current_url = "https://example.test/webtables"
    third = await snapshotter.capture(page)

    assert first == second
    assert third != second
    assert adapter.calls == 2
