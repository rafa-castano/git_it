import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_INGESTION_ROOT = PROJECT_ROOT / "src" / "git_it" / "repository_ingestion"


def test_domain_layer_does_not_import_outer_layers() -> None:
    forbidden_prefixes = (
        "git_it.repository_ingestion.application",
        "git_it.repository_ingestion.infrastructure",
        "git_it.repository_ingestion.interfaces",
        "git_it.repository_ingestion.composition",
    )

    assert_forbidden_imports_absent(
        layer_path=REPOSITORY_INGESTION_ROOT / "domain",
        forbidden_prefixes=forbidden_prefixes,
    )


def test_application_layer_does_not_import_adapters_or_composition() -> None:
    forbidden_prefixes = (
        "git_it.repository_ingestion.infrastructure",
        "git_it.repository_ingestion.interfaces",
        "git_it.repository_ingestion.composition",
    )

    assert_forbidden_imports_absent(
        layer_path=REPOSITORY_INGESTION_ROOT / "application",
        forbidden_prefixes=forbidden_prefixes,
    )


def assert_forbidden_imports_absent(
    *,
    layer_path: Path,
    forbidden_prefixes: tuple[str, ...],
) -> None:
    violations: list[str] = []
    for python_file in layer_path.rglob("*.py"):
        tree = ast.parse(python_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported_modules = imported_module_names(node)
            for imported_module in imported_modules:
                if imported_module.startswith(forbidden_prefixes):
                    relative_path = python_file.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative_path}: {imported_module}")

    assert violations == []


def imported_module_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module is not None:
        return [node.module]
    return []
