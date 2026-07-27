import shutil
from pathlib import Path
from threading import Lock

from app.data_ingestion.lobster import iter_manifests
from app.data_ingestion.models import DatasetManifest, ImportAccepted, ImportedDataset, LobsterCandidate
from app.data_ingestion.sources import LobsterBatchSourceAdapter


class DataIngestionService:
    def __init__(self, raw_dir: Path, processed_dir: Path) -> None:
        self.raw_dir = raw_dir.resolve()
        self.processed_dir = processed_dir.resolve()
        self.lobster = LobsterBatchSourceAdapter(self.raw_dir, self.processed_dir)
        self._import_lock = Lock()
        self._job_lock = Lock()
        self._jobs: dict[str, tuple[str, str | None]] = {}

    def candidates(self) -> list[LobsterCandidate]:
        candidates = self.lobster.candidates()
        with self._job_lock:
            jobs = dict(self._jobs)
        for candidate in candidates:
            job = jobs.get(candidate.candidate_id)
            if not job or candidate.status == "imported":
                continue
            status, detail = job
            if status == "importing":
                candidate.status = "importing"
            elif status == "failed":
                candidate.status = "failed"
                candidate.errors = [detail or "import failed"]
        return candidates

    def datasets(self) -> list[ImportedDataset]:
        return [
            ImportedDataset.from_manifest(manifest, str(path))
            for manifest, path in iter_manifests(self.processed_dir)
        ]

    def dataset(self, dataset_id: str) -> ImportedDataset | None:
        return next((item for item in self.datasets() if item.dataset_id == dataset_id), None)

    def delete_dataset(self, dataset_id: str) -> None:
        with self._import_lock:
            dataset = next(
                (
                    (manifest, path)
                    for manifest, path in iter_manifests(self.processed_dir)
                    if manifest.dataset_id == dataset_id
                ),
                None,
            )
            if dataset is None:
                raise LookupError(dataset_id)
            _, path = dataset
            resolved = path.resolve()
            if not resolved.is_relative_to(self.processed_dir) or resolved.parent != self.processed_dir:
                raise ValueError("dataset path is outside the processed data directory")
            shutil.rmtree(resolved)

    def import_candidate(
        self,
        candidate_id: str,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> DatasetManifest:
        with self._import_lock:
            candidate = next((item for item in self.candidates() if item.candidate_id == candidate_id), None)
            if candidate is None:
                raise LookupError(candidate_id)
            if candidate.status == "invalid":
                raise ValueError("; ".join(candidate.errors))
            return self.lobster.import_candidate(
                candidate,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )

    def begin_import(
        self,
        candidate_id: str,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> tuple[ImportAccepted, bool]:
        candidate = next((item for item in self.candidates() if item.candidate_id == candidate_id), None)
        if candidate is None:
            raise LookupError(candidate_id)
        if candidate.status == "invalid":
            raise ValueError("; ".join(candidate.errors))
        effective_start = candidate.start_time_ms if start_time_ms is None else start_time_ms
        effective_end = candidate.end_time_ms if end_time_ms is None else end_time_ms
        if effective_start < candidate.start_time_ms or effective_end > candidate.end_time_ms:
            raise ValueError("selected time window must be inside the source dataset range")
        if effective_start >= effective_end:
            raise ValueError("selected time window start must be before its end")
        full_window = effective_start == candidate.start_time_ms and effective_end == candidate.end_time_ms
        if candidate.status == "imported" and full_window:
            return (
                ImportAccepted(
                    candidate_id=candidate_id,
                    status="imported",
                    dataset_id=candidate.dataset_id,
                ),
                False,
            )
        with self._job_lock:
            if self._jobs.get(candidate_id, (None, None))[0] == "importing":
                return ImportAccepted(candidate_id=candidate_id, status="importing"), False
            self._jobs[candidate_id] = ("importing", None)
        return ImportAccepted(candidate_id=candidate_id, status="importing"), True

    def execute_import(
        self,
        candidate_id: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> None:
        try:
            self.import_candidate(
                candidate_id,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )
        except Exception as exc:  # Background task must surface errors through discovery status.
            with self._job_lock:
                self._jobs[candidate_id] = ("failed", str(exc))
            return
        with self._job_lock:
            self._jobs.pop(candidate_id, None)
