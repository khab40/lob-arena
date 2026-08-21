from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import Counter
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


LOGGER = logging.getLogger("mlflow-exporter")

DEFAULT_EXPERIMENTS = (
    "lob-arena/corpus-releases",
    "lob-arena/lightgbm-development",
    "lob-arena/governed-evaluation",
)
DEFAULT_METRIC_KEYS = (
    "precision",
    "recall",
    "f1",
    "false_alerts_per_million_events",
    "cloud_wall_seconds",
    "cloud_cpu_seconds",
    "cloud_peak_rss_bytes",
    "cloud_rows_per_second",
    "cloud_estimated_cost_usd",
)
DEFAULT_MODEL_NAMES = ("lob-arena-lightgbm-attack-active",)
RUN_STATUSES = ("RUNNING", "SCHEDULED", "FINISHED", "FAILED", "KILLED", "OTHER")
MODEL_VERSION_STATUSES = ("READY", "PENDING_REGISTRATION", "FAILED_REGISTRATION", "OTHER")


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"required environment variable is empty: {name}")
    return value


def secret(name: str, minimum_length: int = 16) -> str:
    value = required(name)
    if "validation-only" in value or "replace-with-generated-secret" in value:
        raise SystemExit(f"{name} contains a non-deployment placeholder")
    if len(value) < minimum_length:
        raise SystemExit(f"{name} must contain at least {minimum_length} characters")
    return value


def _csv(name: str, default: tuple[str, ...], *, maximum_items: int = 32) -> tuple[str, ...]:
    raw = os.environ.get(name)
    values = default if raw is None else tuple(item.strip() for item in raw.split(",") if item.strip())
    values = tuple(dict.fromkeys(values))
    if not values:
        raise SystemExit(f"{name} must contain at least one value")
    if len(values) > maximum_items:
        raise SystemExit(f"{name} must contain at most {maximum_items} values")
    return values


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise SystemExit(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise SystemExit(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class ExporterConfig:
    experiments: tuple[str, ...]
    metric_keys: tuple[str, ...]
    model_names: tuple[str, ...]
    max_runs_per_experiment: int
    max_model_versions: int
    cache_seconds: int

    @classmethod
    def from_environment(cls) -> "ExporterConfig":
        return cls(
            experiments=_csv("MLFLOW_EXPORTER_EXPERIMENTS", DEFAULT_EXPERIMENTS),
            metric_keys=_csv("MLFLOW_EXPORTER_METRIC_KEYS", DEFAULT_METRIC_KEYS),
            model_names=_csv("MLFLOW_EXPORTER_MODEL_NAMES", DEFAULT_MODEL_NAMES),
            max_runs_per_experiment=_integer(
                "MLFLOW_EXPORTER_MAX_RUNS_PER_EXPERIMENT",
                1000,
                minimum=1,
                maximum=49999,
            ),
            max_model_versions=_integer(
                "MLFLOW_EXPORTER_MAX_MODEL_VERSIONS",
                1000,
                minimum=1,
                maximum=9999,
            ),
            cache_seconds=_integer("MLFLOW_EXPORTER_CACHE_SECONDS", 30, minimum=5, maximum=3600),
        )


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_value(value: float | int) -> str:
    numeric = float(value)
    if math.isnan(numeric):
        return "NaN"
    if math.isinf(numeric):
        return "+Inf" if numeric > 0 else "-Inf"
    return format(numeric, ".17g")


class PrometheusText:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def family(self, name: str, help_text: str, metric_type: str = "gauge") -> None:
        self._lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} {metric_type}"))

    def sample(self, name: str, value: float | int, **labels: object) -> None:
        suffix = ""
        if labels:
            rendered = ",".join(f'{key}="{_escape_label(labels[key])}"' for key in sorted(labels))
            suffix = f"{{{rendered}}}"
        self._lines.append(f"{name}{suffix} {_format_value(value)}")

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


def _normal_status(value: object, allowed: tuple[str, ...]) -> str:
    status = str(value or "").upper()
    return status if status in allowed else "OTHER"


def _not_found(error: Exception) -> bool:
    return getattr(error, "error_code", None) == "RESOURCE_DOES_NOT_EXIST"


class MlflowMetricsCollector:
    def __init__(self, client: Any, config: ExporterConfig) -> None:
        self.client = client
        self.config = config

    def collect(self) -> str:
        output = PrometheusText()
        self._declare_families(output)
        output.sample("mlflow_exporter_configured_experiments", len(self.config.experiments))
        output.sample("mlflow_exporter_configured_models", len(self.config.model_names))
        for experiment_name in self.config.experiments:
            self._collect_experiment(output, experiment_name)
        for model_name in self.config.model_names:
            self._collect_model(output, model_name)
        return output.render()

    def _declare_families(self, output: PrometheusText) -> None:
        output.family(
            "mlflow_exporter_configured_experiments",
            "Number of allow-listed MLflow experiments configured for collection.",
        )
        output.family(
            "mlflow_exporter_configured_models",
            "Number of allow-listed MLflow registered models configured for collection.",
        )
        output.family(
            "mlflow_experiment_available",
            "Whether an allow-listed MLflow experiment is visible to the exporter.",
        )
        output.family(
            "mlflow_runs_observed",
            "Runs in the bounded, newest-first observation window by experiment and status.",
        )
        output.family(
            "mlflow_run_window_limited",
            "Whether the configured per-experiment run limit truncated the observation window.",
        )
        output.family(
            "mlflow_last_run_end_timestamp_seconds",
            "Most recent run completion time in the observation window by experiment and status.",
        )
        output.family(
            "mlflow_run_duration_seconds",
            "Run duration statistic in the observation window by experiment and status.",
        )
        output.family(
            "mlflow_latest_finished_run_metric",
            "Latest allow-listed metric from a finished run by experiment and metric name.",
        )
        output.family(
            "mlflow_registered_model_available",
            "Whether an allow-listed MLflow registered model is visible to the exporter.",
        )
        output.family(
            "mlflow_registered_model_versions",
            "Registered model versions in the bounded observation window by model and status.",
        )
        output.family(
            "mlflow_model_version_window_limited",
            "Whether the configured per-model version limit truncated the observation window.",
        )

    def _collect_experiment(self, output: PrometheusText, experiment_name: str) -> None:
        experiment = self.client.get_experiment_by_name(experiment_name)
        output.sample(
            "mlflow_experiment_available",
            int(experiment is not None),
            experiment=experiment_name,
        )
        if experiment is None:
            output.sample("mlflow_run_window_limited", 0, experiment=experiment_name)
            for status in RUN_STATUSES:
                output.sample("mlflow_runs_observed", 0, experiment=experiment_name, status=status)
            return

        requested = self.config.max_runs_per_experiment + 1
        runs = list(
            self.client.search_runs(
                experiment_ids=[experiment.experiment_id],
                max_results=requested,
                order_by=["attributes.start_time DESC"],
            )
        )
        limited = len(runs) > self.config.max_runs_per_experiment
        runs = runs[: self.config.max_runs_per_experiment]
        output.sample("mlflow_run_window_limited", int(limited), experiment=experiment_name)

        counts: Counter[str] = Counter()
        durations: dict[str, list[float]] = {status: [] for status in RUN_STATUSES}
        latest_end: dict[str, float] = {}
        latest_finished_run: Any | None = None
        latest_finished_time = -1
        for run in runs:
            status = _normal_status(run.info.status, RUN_STATUSES)
            counts[status] += 1
            start_time = run.info.start_time
            end_time = run.info.end_time
            if start_time is not None and end_time is not None and end_time >= start_time:
                durations[status].append((end_time - start_time) / 1000.0)
                latest_end[status] = max(latest_end.get(status, 0.0), end_time / 1000.0)
            if status == "FINISHED":
                candidate_time = end_time if end_time is not None else start_time
                candidate_time = candidate_time if candidate_time is not None else -1
                if candidate_time > latest_finished_time:
                    latest_finished_time = candidate_time
                    latest_finished_run = run

        for status in RUN_STATUSES:
            output.sample(
                "mlflow_runs_observed",
                counts[status],
                experiment=experiment_name,
                status=status,
            )
            values = durations[status]
            if values:
                output.sample(
                    "mlflow_run_duration_seconds",
                    sum(values) / len(values),
                    experiment=experiment_name,
                    status=status,
                    statistic="average",
                )
                output.sample(
                    "mlflow_run_duration_seconds",
                    max(values),
                    experiment=experiment_name,
                    status=status,
                    statistic="maximum",
                )
                output.sample(
                    "mlflow_last_run_end_timestamp_seconds",
                    latest_end[status],
                    experiment=experiment_name,
                    status=status,
                )
        if latest_finished_run is not None:
            for metric_name in self.config.metric_keys:
                if metric_name in latest_finished_run.data.metrics:
                    output.sample(
                        "mlflow_latest_finished_run_metric",
                        float(latest_finished_run.data.metrics[metric_name]),
                        experiment=experiment_name,
                        metric=metric_name,
                    )

    def _collect_model(self, output: PrometheusText, model_name: str) -> None:
        try:
            model = self.client.get_registered_model(model_name)
        except Exception as error:
            if not _not_found(error):
                raise
            model = None
        output.sample("mlflow_registered_model_available", int(model is not None), model=model_name)
        if model is None:
            output.sample("mlflow_model_version_window_limited", 0, model=model_name)
            for status in MODEL_VERSION_STATUSES:
                output.sample("mlflow_registered_model_versions", 0, model=model_name, status=status)
            return

        if "'" in model_name or "\\" in model_name:
            raise ValueError("configured MLflow model names may not contain quotes or backslashes")
        requested = self.config.max_model_versions + 1
        versions = list(
            self.client.search_model_versions(
                filter_string=f"name = '{model_name}'",
                max_results=requested,
                order_by=["version_number DESC"],
            )
        )
        limited = len(versions) > self.config.max_model_versions
        versions = versions[: self.config.max_model_versions]
        output.sample("mlflow_model_version_window_limited", int(limited), model=model_name)
        counts = Counter(
            _normal_status(version.status, MODEL_VERSION_STATUSES) for version in versions
        )
        for status in MODEL_VERSION_STATUSES:
            output.sample(
                "mlflow_registered_model_versions",
                counts[status],
                model=model_name,
                status=status,
            )


class MetricsCache:
    def __init__(
        self,
        collect: Callable[[], str],
        cache_seconds: int,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._collect = collect
        self._cache_seconds = cache_seconds
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._lock = threading.Lock()
        self._last_attempt_monotonic = float("-inf")
        self._last_success_timestamp = 0.0
        self._collection_duration = 0.0
        self._collection_errors = 0
        self._up = False
        self._domain_metrics = ""

    @property
    def ready(self) -> bool:
        return self._up

    def render(self) -> str:
        with self._lock:
            now = self._monotonic()
            if now - self._last_attempt_monotonic >= self._cache_seconds:
                self._refresh(now)
            output = PrometheusText()
            output.family(
                "mlflow_exporter_up",
                "Whether the most recent MLflow collection completed successfully.",
            )
            output.sample("mlflow_exporter_up", int(self._up))
            output.family(
                "mlflow_exporter_last_success_timestamp_seconds",
                "Unix timestamp of the most recent successful MLflow collection.",
            )
            output.sample(
                "mlflow_exporter_last_success_timestamp_seconds",
                self._last_success_timestamp,
            )
            output.family(
                "mlflow_exporter_collection_duration_seconds",
                "Duration of the most recent MLflow collection.",
            )
            output.sample(
                "mlflow_exporter_collection_duration_seconds",
                self._collection_duration,
            )
            output.family(
                "mlflow_exporter_collection_errors_total",
                "MLflow collection failures since the exporter process started.",
                metric_type="counter",
            )
            output.sample("mlflow_exporter_collection_errors_total", self._collection_errors)
            return output.render() + self._domain_metrics

    def _refresh(self, started: float) -> None:
        self._last_attempt_monotonic = started
        try:
            domain_metrics = self._collect()
        except Exception:
            self._collection_errors += 1
            self._up = False
            LOGGER.exception("MLflow metric collection failed")
        else:
            self._domain_metrics = domain_metrics
            self._last_success_timestamp = self._wall_clock()
            self._up = True
        finally:
            self._collection_duration = max(0.0, self._monotonic() - started)


class ExporterServer(ThreadingHTTPServer):
    metrics_cache: MetricsCache


class MetricsHandler(BaseHTTPRequestHandler):
    server: ExporterServer

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._respond(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if self.path == "/ready":
            self.server.metrics_cache.render()
            status = 200 if self.server.metrics_cache.ready else 503
            self._respond(status, b"ready\n" if status == 200 else b"not ready\n")
            return
        if self.path == "/metrics":
            body = self.server.metrics_cache.render().encode("utf-8")
            self._respond(200, body, "text/plain; version=0.0.4; charset=utf-8")
            return
        self._respond(404, b"not found\n")

    def _respond(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.debug(format_string, *args)


def configure_client() -> Any:
    from mlflow import MlflowClient

    tracking_uri = required("MLFLOW_TRACKING_URI")
    os.environ["MLFLOW_TRACKING_USERNAME"] = required("MLFLOW_EXPORTER_USERNAME")
    os.environ["MLFLOW_TRACKING_PASSWORD"] = secret("MLFLOW_EXPORTER_PASSWORD")
    return MlflowClient(tracking_uri=tracking_uri)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    config = ExporterConfig.from_environment()
    collector = MlflowMetricsCollector(configure_client(), config)
    cache = MetricsCache(collector.collect, config.cache_seconds)
    host = os.environ.get("MLFLOW_EXPORTER_HOST", "0.0.0.0")
    port = _integer("MLFLOW_EXPORTER_PORT", 9464, minimum=1, maximum=65535)
    server = ExporterServer((host, port), MetricsHandler)
    server.metrics_cache = cache
    LOGGER.info(
        "Starting MLflow Prometheus exporter on %s:%s for %s experiments and %s models",
        host,
        port,
        len(config.experiments),
        len(config.model_names),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
