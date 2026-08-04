from pathlib import Path
from typing import Protocol

from app.data_ingestion.itch import convert_itch, discover_candidates as discover_itch_candidates
from app.data_ingestion.lobster import convert_pair, discover_candidates
from app.data_ingestion.models import DatasetManifest, IngestionCandidate


class IngestionSourceAdapter(Protocol):
    """Administrative source boundary; later adapters may discover other batch or live inputs."""

    source_type: str
    ingestion_mode: str

    def candidates(self) -> list[IngestionCandidate]:
        ...

    def import_candidate(
        self,
        candidate: IngestionCandidate,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        depth: int | None = None,
    ) -> DatasetManifest:
        ...


class LobsterBatchSourceAdapter:
    source_type = "lobster"
    ingestion_mode = "batch"

    def __init__(self, raw_dir: Path, processed_dir: Path) -> None:
        self.raw_dir = raw_dir.resolve()
        self.processed_dir = processed_dir.resolve()

    def candidates(self) -> list[IngestionCandidate]:
        return discover_candidates(self.raw_dir, self.processed_dir)

    def import_candidate(
        self,
        candidate: IngestionCandidate,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        depth: int | None = None,
    ) -> DatasetManifest:
        return convert_pair(
            candidate,
            self.raw_dir,
            self.processed_dir,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )


class NasdaqItchBatchSourceAdapter:
    source_type = "nasdaq_itch"
    ingestion_mode = "streaming"

    def __init__(self, raw_dir: Path, processed_dir: Path) -> None:
        self.raw_dir = raw_dir.resolve()
        self.processed_dir = processed_dir.resolve()

    def candidates(self) -> list[IngestionCandidate]:
        return discover_itch_candidates(self.raw_dir, self.processed_dir)

    def import_candidate(
        self,
        candidate: IngestionCandidate,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        depth: int | None = None,
    ) -> DatasetManifest:
        return convert_itch(
            candidate,
            self.raw_dir,
            self.processed_dir,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            depth=depth,
        )
