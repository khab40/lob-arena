import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.routes_arena import router as arena_router
from app.api.routes_data_ingestion import router as data_ingestion_router
from app.api.routes_experiments import router as experiments_router
from app.api.routes_health import router as health_router
from app.api.routes_incidents import router as incidents_router
from app.api.routes_nebius import nebius_client, router as nebius_router
from app.api.routes_red_team import router as red_team_router
from app.api.routes_scenarios import router as scenarios_router
from app.api.routes_simulation import router as simulation_router
from app.arena.java_client import JavaArenaClient
from app.config import get_settings
from app.data_ingestion.service import DataIngestionService
from app.metrics import PrometheusTextRegistry
from app.nebius.detector_tournament import DetectorTournamentMetrics
from app.nebius.evidence_archive import configure_default_evidence_archive
from app.storage.local_store import LocalStore
from app.storage.retention import cleanup_output_data

app = FastAPI(title="LOB Arena")
settings = get_settings()
metrics_registry = PrometheusTextRegistry()
metrics_registry.counter(
    "backend_java_arena_requests_total",
    "Requests from FastAPI to the Java arena.",
    ("method", "endpoint", "outcome"),
)
metrics_registry.histogram(
    "backend_java_arena_request_duration_seconds",
    "Request latency from FastAPI to the Java arena.",
    ("method", "endpoint", "outcome"),
)
app.state.tournament_metrics = DetectorTournamentMetrics(metrics_registry)
app.state.store = LocalStore(settings.arena_output_dir)
app.state.nebius_evidence = (
    configure_default_evidence_archive(app.state.store, settings)
    if settings.nebius_evidence_archive_enabled
    else None
)
app.state.retention_cleanup = cleanup_output_data(app.state.store.output_dir, settings.arena_data_retention_days)
app.state.settings = settings
app.state.data_ingestion = DataIngestionService(
    settings.arena_lobster_raw_dir,
    settings.arena_historical_data_dir,
)
app.state.simulation = JavaArenaClient(
    settings.java_arena_base_url,
    timeout_seconds=settings.java_arena_timeout_seconds,
    metrics=metrics_registry,
)
app.state.arena_metrics_snapshot = None
app.state.arena_metrics_snapshot_at = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(arena_router)
app.include_router(data_ingestion_router)
app.include_router(simulation_router)
app.include_router(experiments_router)
app.include_router(scenarios_router)
app.include_router(incidents_router)
app.include_router(nebius_router)
app.include_router(red_team_router)


@app.get("/api/status", tags=["status"])
def api_status() -> dict[str, object]:
    return {
        "service": "lob-arena-backend",
        "status": "ok",
        "nebius": nebius_client.integration_status().model_dump(mode="json"),
    }


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> PlainTextResponse:
    snapshot_up = 1
    try:
        snapshot = await request.app.state.simulation.get_metrics_snapshot()
    except (LookupError, RuntimeError, ValueError):
        snapshot_up = 0
        snapshot = request.app.state.arena_metrics_snapshot
    else:
        request.app.state.arena_metrics_snapshot = snapshot
        request.app.state.arena_metrics_snapshot_at = time.monotonic()

    observed_at = request.app.state.arena_metrics_snapshot_at
    snapshot_age = "NaN" if observed_at is None else f"{max(0.0, time.monotonic() - observed_at):.6g}"
    lines: list[str] = []
    if snapshot is not None:
        lines.extend(
            [
                "# HELP arena_tick Current simulation tick.",
                "# TYPE arena_tick gauge",
                f"arena_tick {snapshot.tick}",
                "# HELP arena_running Whether the simulation loop is running.",
                "# TYPE arena_running gauge",
                f"arena_running {1 if snapshot.running else 0}",
                "# HELP arena_incidents_total Number of in-memory incidents.",
                "# TYPE arena_incidents_total gauge",
                f"arena_incidents_total {snapshot.incidents_count}",
            ]
        )
    lines.extend(
        [
            "# HELP arena_metrics_snapshot_up Whether the Java metrics snapshot refreshed successfully.",
            "# TYPE arena_metrics_snapshot_up gauge",
            f"arena_metrics_snapshot_up {snapshot_up}",
            "# HELP arena_metrics_snapshot_age_seconds Age of the last successful Java metrics snapshot.",
            "# TYPE arena_metrics_snapshot_age_seconds gauge",
            f"arena_metrics_snapshot_age_seconds {snapshot_age}",
            metrics_registry.render(),
        ]
    )
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4",
    )


@app.on_event("shutdown")
async def shutdown_simulation() -> None:
    await app.state.simulation.stop()
