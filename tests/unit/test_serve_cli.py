"""Tests for the `git-it serve` CLI command — Batch 47."""

import os
from pathlib import Path
from unittest.mock import patch


def test_serve_command_is_registered() -> None:
    """The serve subcommand must be accepted without error (help flag)."""
    from git_it.repository_ingestion.interfaces.cli import main

    # --help exits with 0 and we intercept SystemExit
    try:
        main(["serve", "--help"])
    except SystemExit as exc:
        assert exc.code == 0


def test_serve_defaults_host_and_port(tmp_path: Path) -> None:
    """serve with no flags calls uvicorn with default host 127.0.0.1:8000."""
    from git_it.repository_ingestion.interfaces.cli import main

    prev = os.environ.pop("GIT_IT_DATA_DIR", None)
    try:
        with patch("uvicorn.run") as mock_run:
            result = main(["serve"], project_root=tmp_path)
    finally:
        if prev is None:
            os.environ.pop("GIT_IT_DATA_DIR", None)
        else:
            os.environ["GIT_IT_DATA_DIR"] = prev

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args
    assert call_kwargs.kwargs.get("host") == "127.0.0.1" or call_kwargs.args[1:2] == ("127.0.0.1",)
    assert call_kwargs.kwargs.get("port") == 8000
    assert result == 0


def test_serve_custom_host_and_port(tmp_path: Path) -> None:
    """serve --host 0.0.0.0 --port 9000 passes values to uvicorn."""
    from git_it.repository_ingestion.interfaces.cli import main

    prev = os.environ.pop("GIT_IT_DATA_DIR", None)
    try:
        with patch("uvicorn.run") as mock_run:
            main(["serve", "--host", "0.0.0.0", "--port", "9000"], project_root=tmp_path)
    finally:
        if prev is None:
            os.environ.pop("GIT_IT_DATA_DIR", None)
        else:
            os.environ["GIT_IT_DATA_DIR"] = prev

    call_kwargs = mock_run.call_args
    assert call_kwargs.kwargs.get("host") == "0.0.0.0"
    assert call_kwargs.kwargs.get("port") == 9000


def test_serve_sets_git_it_data_dir_env(tmp_path: Path) -> None:
    """serve must set GIT_IT_DATA_DIR so the module-level app picks up the right path."""
    from git_it.repository_ingestion.interfaces.cli import main

    captured_env: dict[str, str | None] = {}

    def fake_uvicorn_run(*args: object, **kwargs: object) -> None:
        captured_env["GIT_IT_DATA_DIR"] = os.environ.get("GIT_IT_DATA_DIR")

    prev = os.environ.pop("GIT_IT_DATA_DIR", None)
    try:
        with patch("uvicorn.run", side_effect=fake_uvicorn_run):
            main(["serve"], project_root=tmp_path)
    finally:
        if prev is None:
            os.environ.pop("GIT_IT_DATA_DIR", None)
        else:
            os.environ["GIT_IT_DATA_DIR"] = prev

    assert captured_env["GIT_IT_DATA_DIR"] == str(tmp_path)
