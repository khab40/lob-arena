from __future__ import annotations

from types import SimpleNamespace

import pytest

from deployments.mlflow.exporter import ExporterConfig, MetricsCache, MlflowMetricsCollector
from deployments.mlflow.exporter_bootstrap import _ensure_exporter_user, _reconcile_permissions


def _run(
    status: str,
    *,
    start_time: int,
    end_time: int | None,
    metrics: dict[str, float] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(status=status, start_time=start_time, end_time=end_time),
        data=SimpleNamespace(metrics=metrics or {}),
    )


class NotFoundError(Exception):
    error_code = "RESOURCE_DOES_NOT_EXIST"


class FakeMlflowClient:
    def __init__(self) -> None:
        self.experiments = {
            "governed": SimpleNamespace(experiment_id="exp-1"),
        }
        self.runs = {
            "exp-1": [
                _run(
                    "FINISHED",
                    start_time=1_000,
                    end_time=6_000,
                    metrics={"precision": 0.97},
                ),
                _run("FAILED", start_time=2_000, end_time=4_000),
                _run(
                    "FINISHED",
                    start_time=500,
                    end_time=3_500,
                    metrics={"precision": 0.91, "recall": 0.81},
                ),
            ],
        }
        self.models = {"detector": SimpleNamespace(name="detector")}
        self.versions = [
            SimpleNamespace(status="READY"),
            SimpleNamespace(status="READY"),
            SimpleNamespace(status="FAILED_REGISTRATION"),
        ]

    def get_experiment_by_name(self, name: str) -> SimpleNamespace | None:
        return self.experiments.get(name)

    def search_runs(self, experiment_ids: list[str], **_: object) -> list[SimpleNamespace]:
        return self.runs[experiment_ids[0]]

    def get_registered_model(self, name: str) -> SimpleNamespace:
        if name not in self.models:
            raise NotFoundError(name)
        return self.models[name]

    def search_model_versions(self, **_: object) -> list[SimpleNamespace]:
        return self.versions


def _config(**overrides: object) -> ExporterConfig:
    values = {
        "experiments": ("governed",),
        "metric_keys": ("precision", "recall"),
        "model_names": ("detector",),
        "max_runs_per_experiment": 10,
        "max_model_versions": 10,
        "cache_seconds": 30,
    }
    values.update(overrides)
    return ExporterConfig(**values)


def test_collector_exports_bounded_run_and_model_aggregates() -> None:
    rendered = MlflowMetricsCollector(FakeMlflowClient(), _config()).collect()

    assert 'mlflow_experiment_available{experiment="governed"} 1' in rendered
    assert 'mlflow_runs_observed{experiment="governed",status="FINISHED"} 2' in rendered
    assert 'mlflow_runs_observed{experiment="governed",status="FAILED"} 1' in rendered
    assert (
        'mlflow_run_duration_seconds{experiment="governed",statistic="average",status="FINISHED"} 4'
        in rendered
    )
    assert (
        'mlflow_latest_finished_run_metric{experiment="governed",metric="precision"} '
        "0.96999999999999997"
    ) in rendered
    assert 'mlflow_latest_finished_run_metric{experiment="governed",metric="recall"}' not in rendered
    assert (
        'mlflow_registered_model_versions{model="detector",status="READY"} 2'
        in rendered
    )
    assert "run_id" not in rendered


def test_collector_reports_missing_resources_without_unbounded_labels() -> None:
    rendered = MlflowMetricsCollector(
        FakeMlflowClient(),
        _config(experiments=("missing",), model_names=("missing-model",)),
    ).collect()

    assert 'mlflow_experiment_available{experiment="missing"} 0' in rendered
    assert 'mlflow_runs_observed{experiment="missing",status="FINISHED"} 0' in rendered
    assert 'mlflow_registered_model_available{model="missing-model"} 0' in rendered
    assert (
        'mlflow_registered_model_versions{model="missing-model",status="READY"} 0'
        in rendered
    )


def test_collector_marks_truncated_observation_windows() -> None:
    rendered = MlflowMetricsCollector(
        FakeMlflowClient(),
        _config(max_runs_per_experiment=2, max_model_versions=2),
    ).collect()

    assert 'mlflow_run_window_limited{experiment="governed"} 1' in rendered
    assert 'mlflow_model_version_window_limited{model="detector"} 1' in rendered
    assert 'mlflow_runs_observed{experiment="governed",status="FINISHED"} 1' in rendered
    assert 'mlflow_registered_model_versions{model="detector",status="READY"} 2' in rendered


def test_metrics_cache_preserves_last_snapshot_and_reports_collection_failure() -> None:
    monotonic_time = [100.0]
    wall_time = [1_700_000_000.0]
    should_fail = [False]

    def collect() -> str:
        if should_fail[0]:
            raise RuntimeError("tracking server unavailable")
        return "mlflow_test_domain_metric 7\n"

    cache = MetricsCache(
        collect,
        30,
        monotonic=lambda: monotonic_time[0],
        wall_clock=lambda: wall_time[0],
    )
    first = cache.render()
    assert "mlflow_exporter_up 1" in first
    assert "mlflow_exporter_last_success_timestamp_seconds 1700000000" in first
    assert "mlflow_test_domain_metric 7" in first

    should_fail[0] = True
    monotonic_time[0] += 31
    second = cache.render()
    assert "mlflow_exporter_up 0" in second
    assert "mlflow_exporter_collection_errors_total 1" in second
    assert "mlflow_test_domain_metric 7" in second


def test_exporter_configuration_is_allow_listed_and_deduplicated(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_EXPORTER_EXPERIMENTS", "one,two,one")
    monkeypatch.setenv("MLFLOW_EXPORTER_METRIC_KEYS", "precision,recall")
    monkeypatch.setenv("MLFLOW_EXPORTER_MODEL_NAMES", "detector")
    monkeypatch.setenv("MLFLOW_EXPORTER_MAX_RUNS_PER_EXPERIMENT", "50")
    monkeypatch.setenv("MLFLOW_EXPORTER_MAX_MODEL_VERSIONS", "25")
    monkeypatch.setenv("MLFLOW_EXPORTER_CACHE_SECONDS", "45")

    config = ExporterConfig.from_environment()

    assert config.experiments == ("one", "two")
    assert config.metric_keys == ("precision", "recall")
    assert config.model_names == ("detector",)
    assert config.max_runs_per_experiment == 50
    assert config.max_model_versions == 25
    assert config.cache_seconds == 45


def test_exporter_bootstrap_rejects_admin_before_password_update() -> None:
    admin = SimpleNamespace(id=1, username="admin", is_admin=True)

    class FakeAuthClient:
        password_updates: list[tuple[str, str]] = []

        def get_user(self, username: str) -> SimpleNamespace:
            assert username == "admin"
            return admin

        def update_user_password(self, username: str, password: str) -> None:
            self.password_updates.append((username, password))

    auth_client = FakeAuthClient()

    with pytest.raises(RuntimeError, match="must not be an administrator"):
        _ensure_exporter_user(auth_client, "admin", "exporter-password")

    assert auth_client.password_updates == []


def test_exporter_bootstrap_reconciles_stale_direct_permissions() -> None:
    user = SimpleNamespace(id=7, username="prometheus", is_admin=False)
    personal_role = SimpleNamespace(id=12, name="__user_7__")
    permissions = [
        SimpleNamespace(
            resource_type="experiment",
            resource_pattern="keep-experiment",
            permission="READ",
        ),
        SimpleNamespace(
            resource_type="experiment",
            resource_pattern="stale-experiment",
            permission="READ",
        ),
        SimpleNamespace(
            resource_type="registered_model",
            resource_pattern="stale-model",
            permission="READ",
        ),
        SimpleNamespace(
            resource_type="workspace",
            resource_pattern="*",
            permission="USE",
        ),
    ]

    class FakeAuthClient:
        revoked: list[tuple[str, str, str]] = []
        granted: list[tuple[str, str, str, str]] = []

        def list_all_roles(self) -> list[SimpleNamespace]:
            return [personal_role]

        def list_role_permissions(self, role_id: int) -> list[SimpleNamespace]:
            assert role_id == personal_role.id
            return permissions

        def revoke_user_permission(
            self,
            username: str,
            *,
            resource_type: str,
            resource_id: str,
        ) -> None:
            self.revoked.append((username, resource_type, resource_id))

        def grant_user_permission(
            self,
            username: str,
            *,
            resource_type: str,
            resource_id: str,
            permission: str,
        ) -> None:
            self.granted.append((username, resource_type, resource_id, permission))

    auth_client = FakeAuthClient()
    desired = {
        ("experiment", "keep-experiment"),
        ("registered_model", "current-model"),
    }

    _reconcile_permissions(auth_client, user, desired)

    assert auth_client.revoked == [
        ("prometheus", "experiment", "stale-experiment"),
        ("prometheus", "registered_model", "stale-model"),
    ]
    assert auth_client.granted == [
        ("prometheus", "registered_model", "current-model", "READ"),
    ]


def test_exporter_bootstrap_grants_permissions_before_personal_role_exists() -> None:
    user = SimpleNamespace(id=8, username="new-exporter", is_admin=False)

    class FakeAuthClient:
        granted: list[tuple[str, str, str, str]] = []

        def list_all_roles(self) -> list[SimpleNamespace]:
            return []

        def grant_user_permission(
            self,
            username: str,
            *,
            resource_type: str,
            resource_id: str,
            permission: str,
        ) -> None:
            self.granted.append((username, resource_type, resource_id, permission))

    auth_client = FakeAuthClient()

    _reconcile_permissions(auth_client, user, {("experiment", "first-experiment")})

    assert auth_client.granted == [
        ("new-exporter", "experiment", "first-experiment", "READ"),
    ]
