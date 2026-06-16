from git_it.repository_ingestion.application.ports import FileFactReader
from git_it.repository_ingestion.domain.patterns import Hotspot, PatternReport

_DEFAULT_HOTSPOT_THRESHOLD = 5


class PatternDetectionService:
    def __init__(self, *, reader: FileFactReader) -> None:
        self._reader = reader

    def detect(
        self,
        repository_id: str,
        *,
        hotspot_threshold: int = _DEFAULT_HOTSPOT_THRESHOLD,
    ) -> PatternReport:
        churn_records = self._reader.get_file_churn(repository_id)
        hotspots = sorted(
            (
                Hotspot(
                    file_path=r.file_path,
                    commit_count=r.commit_count,
                    total_insertions=r.total_insertions,
                    total_deletions=r.total_deletions,
                )
                for r in churn_records
                if r.commit_count >= hotspot_threshold
            ),
            key=lambda h: h.commit_count,
            reverse=True,
        )
        return PatternReport(repository_id=repository_id, hotspots=hotspots)
