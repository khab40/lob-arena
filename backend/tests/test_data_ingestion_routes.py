from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_data_ingestion import router
from app.data_ingestion.models import ImportAccepted


class StubIngestion:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.discovery: list[tuple[str, str | None]] = []
        self.imports: list[tuple[object, ...]] = []

    def delete_dataset(self, dataset_id: str) -> None:
        self.deleted.append(dataset_id)

    def candidates(self, source_type: str, symbol: str | None = None) -> list[object]:
        self.discovery.append((source_type, symbol))
        return []

    def begin_import(self, candidate_id: str, **options: object) -> tuple[ImportAccepted, bool]:
        self.imports.append(("begin", candidate_id, options))
        return ImportAccepted(candidate_id=candidate_id, status="importing"), True

    def execute_import(self, *args: object) -> None:
        self.imports.append(("execute", *args))


class StubSimulation:
    def __init__(self, dataset_id: str | None = None, failure: Exception | None = None) -> None:
        self.dataset_id = dataset_id
        self.failure = failure

    async def get_state(self) -> SimpleNamespace:
        if self.failure is not None:
            raise self.failure
        market_data = None if self.dataset_id is None else {"dataset_id": self.dataset_id}
        return SimpleNamespace(market_data=market_data)


def client_for(simulation: StubSimulation) -> tuple[TestClient, StubIngestion]:
    app = FastAPI()
    ingestion = StubIngestion()
    app.state.data_ingestion = ingestion
    app.state.simulation = simulation
    app.include_router(router)
    return TestClient(app), ingestion


def test_delete_dataset_rejects_dataset_loaded_by_arena() -> None:
    client, ingestion = client_for(StubSimulation(dataset_id="dataset-active"))

    response = client.delete("/api/data-ingestion/datasets/dataset-active")

    assert response.status_code == 409
    assert "currently loaded" in response.json()["detail"]
    assert ingestion.deleted == []


def test_delete_dataset_removes_dataset_not_loaded_by_arena() -> None:
    client, ingestion = client_for(StubSimulation(dataset_id="dataset-other"))

    response = client.delete("/api/data-ingestion/datasets/dataset-stale")

    assert response.status_code == 204
    assert ingestion.deleted == ["dataset-stale"]


def test_delete_dataset_fails_closed_when_arena_state_is_unavailable() -> None:
    client, ingestion = client_for(StubSimulation(failure=RuntimeError("offline")))

    response = client.delete("/api/data-ingestion/datasets/dataset-stale")

    assert response.status_code == 503
    assert "safely delete" in response.json()["detail"]
    assert ingestion.deleted == []


def test_source_neutral_discovery_and_import_forward_adapter_options() -> None:
    client, ingestion = client_for(StubSimulation())

    discovery = client.get("/api/data-ingestion/sources/nasdaq_itch/candidates?symbol=AAPL")
    imported = client.post(
        "/api/data-ingestion/sources/nasdaq_itch/candidates/candidate-1/import",
        json={"start_time_ms": 34_200_000, "end_time_ms": 36_000_000, "depth": 10},
    )

    assert discovery.status_code == 200
    assert ingestion.discovery == [("nasdaq_itch", "AAPL")]
    assert imported.status_code == 202
    assert imported.json()["status"] == "importing"
    assert ingestion.imports[0] == (
        "begin",
        "candidate-1",
        {
            "start_time_ms": 34_200_000,
            "end_time_ms": 36_000_000,
            "depth": 10,
            "source_type": "nasdaq_itch",
        },
    )
    assert ingestion.imports[1] == (
        "execute",
        "candidate-1",
        34_200_000,
        36_000_000,
        10,
        "nasdaq_itch",
    )
