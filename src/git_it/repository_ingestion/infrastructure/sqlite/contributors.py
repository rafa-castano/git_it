import re
import sqlite3
from pathlib import Path

from git_it.repository_ingestion.application.ports import ContributorRecord

from ._common import _extract_github_username

_BOT_PATTERN = re.compile(r"\[bot\]|dependabot|copilot|renovate", re.IGNORECASE)


class SqliteContributorReader:
    """Read-side adapter: aggregates per-author statistics from commit_facts."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def _load_login_map(self, repository_id: str) -> dict[str, str | None]:
        """Read the spec 031 ``author_email -> github_login`` map for this repository.

        Tolerates a missing ``author_logins`` table (a DB ingested before spec 031,
        or a read-only caller that never provisioned it) by degrading to an empty map
        — reads must never create tables as a side effect.
        """
        try:
            with sqlite3.connect(self._database_path) as conn:
                rows = conn.execute(
                    "SELECT author_email, github_login FROM author_logins WHERE repository_id = ?",
                    (repository_id,),
                ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {str(row[0]): (str(row[1]) if row[1] is not None else None) for row in rows}

    def list_contributors(self, repository_id: str) -> list[ContributorRecord]:
        login_map = self._load_login_map(repository_id)
        with sqlite3.connect(self._database_path) as conn:
            cur = conn.cursor()

            # Per-author commit stats
            cur.execute(
                """
                SELECT author_name,
                       COUNT(*) AS commit_count,
                       MIN(committed_at) AS first_commit,
                       MAX(committed_at) AS last_commit,
                       COUNT(DISTINCT SUBSTR(committed_at, 1, 10)) AS active_days,
                       MAX(author_email) AS author_email
                FROM commit_facts
                WHERE repository_id = ?
                GROUP BY author_name
                ORDER BY commit_count DESC
                """,
                (repository_id,),
            )
            author_rows = cur.fetchall()

            if not author_rows:
                return []

            # Category breakdown per author
            cur.execute(
                """
                SELECT cf.author_name,
                       json_extract(ca.data, '$.category') AS category,
                       COUNT(*) AS cnt
                FROM commit_facts cf
                JOIN commit_analyses ca ON ca.repository_id = cf.repository_id
                                        AND ca.commit_sha = cf.sha
                WHERE cf.repository_id = ?
                GROUP BY cf.author_name, category
                """,
                (repository_id,),
            )
            cat_rows = cur.fetchall()
            cat_by_author: dict[str, dict[str, int]] = {}
            for author, cat, cnt in cat_rows:
                if author not in cat_by_author:
                    cat_by_author[author] = {}
                if cat:
                    cat_by_author[author][cat.upper()] = cnt

            # Top files per author
            cur.execute(
                """
                SELECT cf.author_name, ff.file_path, COUNT(*) AS touches
                FROM commit_facts cf
                JOIN file_facts ff ON ff.repository_id = cf.repository_id
                                   AND ff.commit_sha = cf.sha
                WHERE cf.repository_id = ?
                GROUP BY cf.author_name, ff.file_path
                ORDER BY cf.author_name, touches DESC
                """,
                (repository_id,),
            )
            file_rows = cur.fetchall()
            files_by_author: dict[str, list[str]] = {}
            for author, fpath, _ in file_rows:
                if author not in files_by_author:
                    files_by_author[author] = []
                if len(files_by_author[author]) < 5:
                    files_by_author[author].append(fpath)

        return [
            ContributorRecord(
                author_name=name,
                commit_count=count,
                first_commit=(first[:10] if first else None),
                last_commit=(last[:10] if last else None),
                is_bot=bool(_BOT_PATTERN.search(name or "")),
                active_days=active_days,
                github_username=(
                    login_map.get(email or "") or _extract_github_username(email or "")
                ),
                category_counts=cat_by_author.get(name, {}),
                top_files=files_by_author.get(name, []),
            )
            for name, count, first, last, active_days, email in author_rows
        ]
