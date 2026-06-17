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
