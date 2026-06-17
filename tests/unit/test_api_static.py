"""Tests for static file serving and root redirect."""

from pathlib import Path

from fastapi.testclient import TestClient

from git_it.api.app import create_app


def test_root_redirects_to_index(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app, follow_redirects=False)
    response = client.get("/")
    assert response.status_code in (301, 302, 307, 308)
    assert "/static/index.html" in response.headers["location"]


def test_static_index_html_served(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app, follow_redirects=True)
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Git It" in response.text


def test_static_index_contains_api_calls(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "/api/repos" in response.text


def test_openapi_docs_still_available(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200


def test_static_index_contains_chartjs(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "chart.js" in response.text.lower() or "Chart" in response.text


def test_static_index_has_four_tabs(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    for tab in ["Overview", "Case Study", "Patterns", "Commits"]:
        assert tab in response.text


def test_static_index_has_category_colors(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "BUGFIX" in response.text or "bugfix" in response.text.lower()


def test_static_index_has_aria_roles(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert 'role="tablist"' in response.text
    assert 'role="tab"' in response.text
    assert 'role="tabpanel"' in response.text
    assert 'role="tooltip"' in response.text


def test_static_index_has_tooltip_system(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert "TIPS" in response.text
    assert "global-tip" in response.text
    assert "data-tip" in response.text


def test_static_index_lang_attribute(tmp_path: Path) -> None:
    app = create_app(project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/static/index.html")
    assert 'lang="en"' in response.text
