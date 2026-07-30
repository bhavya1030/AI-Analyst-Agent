"""Unit tests for Dataset Source Validator (mocked HTTP)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.validation.dataset_sources import (
    DatasetSourceValidator,
    SourceEntry,
    collect_configured_sources,
    generate_validation_report,
    suggest_replacement,
)


class _FakeResp:
    def __init__(
        self,
        *,
        status=200,
        content=b"Country,Year,Value\nIndia,2020,1\n",
        content_type="text/csv",
        url="https://example.com/data.csv",
        headers=None,
        history=None,
    ):
        self.status_code = status
        self._content = content
        self.url = url
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(content)),
            "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        }
        if headers:
            self.headers.update(headers)
        self.history = history or []

    def iter_content(self, chunk_size=64 * 1024):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_suggest_replacement_inflation_and_oecd():
    assert "worldbank" in (
        suggest_replacement(
            "https://raw.githubusercontent.com/datasets/inflation/master/data/cpi.csv"
        )
        or ""
    ).lower()
    assert suggest_replacement(
        "https://data.oecd.org/searchresults/?q=gdp"
    )


def test_collect_configured_sources_includes_config():
    sources = collect_configured_sources()
    assert sources
    urls = {s.url for s in sources}
    # Known good config keys should appear
    assert any("gdp.csv" in u for u in urls)


def test_validate_healthy_csv():
    content = b"country,year,value\nIndia,2020,1.2\nUSA,2021,2.3\n"
    head = _FakeResp(content=content, content_type="text/csv")
    get = MagicMock(return_value=_FakeResp(content=content, content_type="text/csv"))

    def head_fn(*a, **k):
        return head

    v = DatasetSourceValidator(head=head_fn, get=get)
    result = v.validate_url("https://example.com/data.csv", expected_format="csv")
    assert result.healthy, result.reason
    assert result.status_code == 200
    assert result.file_format == "csv"
    assert result.file_size == len(content)
    assert result.checksum_sha256
    assert result.last_modified


def test_validate_rejects_html():
    html = b"<!DOCTYPE html><html><body>not a dataset</body></html>"
    page_url = "https://example.com/datasets/landing-page"
    head = _FakeResp(content=html, content_type="text/html", url=page_url)
    get = MagicMock(
        return_value=_FakeResp(content=html, content_type="text/html", url=page_url)
    )
    v = DatasetSourceValidator(head=lambda *a, **k: head, get=get)
    result = v.validate_url(page_url)
    assert not result.healthy
    assert "html" in result.reason or (
        result.content_type and "html" in result.content_type
    )


def test_validate_rejects_http_404():
    head = _FakeResp(status=404, content=b"missing", content_type="text/plain")
    get = MagicMock(return_value=_FakeResp(status=404, content=b"missing"))
    v = DatasetSourceValidator(head=lambda *a, **k: head, get=get)
    result = v.validate_url("https://example.com/gone.csv")
    assert not result.healthy
    assert "404" in result.reason


def test_validate_blocked_oecd_search():
    v = DatasetSourceValidator()
    result = v.validate_url("https://data.oecd.org/searchresults/?q=ev")
    assert not result.healthy
    assert "blocked" in result.reason or "oecd" in result.reason
    assert result.suggested_replacement


def test_validate_all_report_and_files(tmp_path):
    content = b"country,year,value\nIndia,2020,1.2\nUSA,2021,2.3\n"
    healthy_url = "https://raw.githubusercontent.com/example/repo/main/data.csv"
    broken_url = "https://data.oecd.org/searchresults/?q=x"

    def head_fn(url, **kwargs):
        if "oecd" in url:
            return _FakeResp(status=403, content=b"no", content_type="text/html", url=url)
        return _FakeResp(content=content, content_type="text/csv", url=url)

    def get_fn(url, **kwargs):
        if "oecd" in url:
            return _FakeResp(status=403, content=b"<!DOCTYPE html><html>", content_type="text/html", url=url)
        return _FakeResp(content=content, content_type="text/csv", url=url)

    v = DatasetSourceValidator(head=head_fn, get=get_fn)
    entries = [
        SourceEntry(key="good", url=healthy_url, origin="test", expected_format="csv"),
        SourceEntry(key="bad", url=broken_url, origin="test"),
    ]
    report = v.validate_all(entries, include_registry=False)
    assert len(report.healthy) == 1
    assert len(report.broken) == 1
    # origin=test is advisory; critical_broken empty → report.ok
    assert report.ok
    assert len(report.advisory_broken) == 1

    paths = generate_validation_report(report, output_dir=tmp_path)
    assert paths["json"].is_file()
    assert paths["markdown"].is_file()
    md = paths["markdown"].read_text(encoding="utf-8")
    assert "Broken Sources" in md
    assert "Healthy Sources" in md


def test_critical_origin_fails_report_ok():
    content = b"country,year,value\nIndia,2020,1.2\n"
    broken_url = "https://data.oecd.org/searchresults/?q=x"

    def head_fn(url, **kwargs):
        return _FakeResp(status=403, content=b"no", content_type="text/html", url=url)

    def get_fn(url, **kwargs):
        return _FakeResp(
            status=403, content=b"<!DOCTYPE html><html>", content_type="text/html", url=url
        )

    v = DatasetSourceValidator(head=head_fn, get=get_fn)
    entries = [
        SourceEntry(key="cfg.gdp", url=broken_url, origin="config", expected_format="csv"),
    ]
    report = v.validate_all(entries, include_registry=False)
    assert len(report.critical_broken) == 1
    assert not report.ok


def test_deactivate_broken_registry_urls(monkeypatch):
    from backend.validation import dataset_sources as ds

    updated = {}

    class Row:
        dataset_id = "abc"
        summary = ""
        download_url = "https://example.com/dead.csv"

        def to_dict(self):
            return {
                "dataset_id": self.dataset_id,
                "title": "Dead",
                "topic": "dead",
                "download_url": self.download_url,
                "summary": self.summary,
                "is_active": True,
            }

    monkeypatch.setattr(
        "backend.registry.get_by_dataset_id",
        lambda dataset_id: Row() if dataset_id == "abc" else None,
    )

    def fake_update(payload):
        updated.update(payload)
        return SimpleNamespace(**payload)

    monkeypatch.setattr("backend.registry.update_dataset", fake_update)

    broken = [
        ds.SourceValidationResult(
            key="registry.abc",
            url="https://example.com/dead.csv",
            origin="registry",
            healthy=False,
            reason="http_status:404",
            suggested_replacement="https://example.com/good.csv",
        )
    ]
    out = ds.deactivate_broken_registry_urls(broken)
    assert len(out) == 1
    assert updated.get("is_active") is False
    assert "AUTO-DISABLED" in (updated.get("summary") or "")
