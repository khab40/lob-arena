from functools import lru_cache
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND_ROOT.parent if _BACKEND_ROOT.name == "backend" else _BACKEND_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LOB Arena"
    endpoint_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ENDPOINT_TOKEN", "NEBIUS_ENDPOINT_TOKEN"),
    )
    nebius_tenant_id: str | None = Field(default=None, alias="NEBIUS_TENANT_ID")
    nebius_endpoint_base_url: str | None = Field(
        default=None,
        alias="NEBIUS_ENDPOINT_BASE_URL",
    )
    nebius_incident_explainer_url: str | None = Field(
        default=None,
        alias="NEBIUS_INCIDENT_EXPLAINER_URL",
    )
    nebius_scenario_generator_url: str | None = Field(
        default=None,
        alias="NEBIUS_SCENARIO_GENERATOR_URL",
    )
    nebius_market_abuse_scenario_url: str | None = Field(
        default=None,
        alias="NEBIUS_MARKET_ABUSE_SCENARIO_URL",
    )
    nebius_orderbook_alert_url: str | None = Field(
        default=None,
        alias="NEBIUS_ORDERBOOK_ALERT_URL",
    )
    nebius_investigation_report_url: str | None = Field(
        default=None,
        alias="NEBIUS_INVESTIGATION_REPORT_URL",
    )
    nebius_investigation_team_url: str | None = Field(
        default=None,
        alias="NEBIUS_INVESTIGATION_TEAM_URL",
    )
    nebius_endpoint_mode: str = Field(default="mock", alias="NEBIUS_ENDPOINT_MODE")
    nebius_job_image: str = Field(
        default="ghcr.io/khab40/lob-arena-jobs:latest",
        alias="NEBIUS_JOB_IMAGE",
    )
    nebius_subnet_id: str | None = Field(default=None, alias="NEBIUS_SUBNET_ID")
    nebius_parent_id: str | None = Field(default=None, alias="NEBIUS_PARENT_ID")
    nebius_volume: str | None = Field(default=None, alias="NEBIUS_VOLUME")
    nebius_job_output_volume: str | None = Field(default=None, alias="NEBIUS_JOB_OUTPUT_VOLUME")
    nebius_job_output_uri: str | None = Field(default=None, alias="NEBIUS_JOB_OUTPUT_URI")
    nebius_object_storage_endpoint_url: str | None = Field(
        default=None,
        alias="NEBIUS_OBJECT_STORAGE_ENDPOINT_URL",
    )
    nebius_object_storage_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
    )
    nebius_object_storage_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
    )
    nebius_object_storage_session_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEBIUS_OBJECT_STORAGE_SESSION_TOKEN", "AWS_SESSION_TOKEN"),
    )
    nebius_object_storage_access_key_secret_id: str | None = Field(
        default=None,
        alias="NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID",
    )
    nebius_object_storage_secret_key_secret_id: str | None = Field(
        default=None,
        alias="NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID",
    )
    nebius_object_storage_session_token_secret_id: str | None = Field(
        default=None,
        alias="NEBIUS_OBJECT_STORAGE_SESSION_TOKEN_SECRET_ID",
    )
    nebius_object_storage_region: str = Field(
        default="eu-north1",
        validation_alias=AliasChoices("NEBIUS_OBJECT_STORAGE_REGION", "AWS_DEFAULT_REGION"),
    )
    nebius_evidence_archive_enabled: bool = Field(
        default=False,
        alias="NEBIUS_EVIDENCE_ARCHIVE_ENABLED",
    )
    nebius_job_submit_command_template: str | None = Field(
        default=None,
        alias="NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE",
    )
    nebius_job_status_command_template: str | None = Field(
        default=None,
        alias="NEBIUS_JOB_STATUS_COMMAND_TEMPLATE",
    )
    nebius_job_logs_command_template: str | None = Field(
        default=None,
        alias="NEBIUS_JOB_LOGS_COMMAND_TEMPLATE",
    )
    nebius_job_artifacts_command_template: str | None = Field(
        default=None,
        alias="NEBIUS_JOB_ARTIFACTS_COMMAND_TEMPLATE",
    )
    nebius_job_health_command: str | None = Field(
        default=None,
        alias="NEBIUS_JOB_HEALTH_COMMAND",
    )
    nebius_cloud_probe_timeout_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        alias="NEBIUS_CLOUD_PROBE_TIMEOUT_SECONDS",
    )
    nebius_health_timeout_seconds: float = Field(
        default=0.5,
        ge=0.05,
        le=5.0,
        alias="NEBIUS_HEALTH_TIMEOUT_SECONDS",
    )
    nebius_inference_timeout_seconds: float = Field(
        default=180.0,
        ge=5.0,
        le=600.0,
        alias="NEBIUS_INFERENCE_TIMEOUT_SECONDS",
    )
    nebius_input_token_cost_per_million_usd: float = Field(
        default=0.0,
        ge=0.0,
        alias="NEBIUS_INPUT_TOKEN_COST_PER_MILLION_USD",
    )
    nebius_output_token_cost_per_million_usd: float = Field(
        default=0.0,
        ge=0.0,
        alias="NEBIUS_OUTPUT_TOKEN_COST_PER_MILLION_USD",
    )
    nebius_job_cost_per_hour_usd: float = Field(
        default=0.0,
        ge=0.0,
        alias="NEBIUS_JOB_COST_PER_HOUR_USD",
    )
    nebius_local_tournament_scenario_limit: int = Field(
        default=24,
        ge=1,
        le=200,
        alias="NEBIUS_LOCAL_TOURNAMENT_SCENARIO_LIMIT",
    )
    arena_output_dir: Path = Field(default=Path("../outputs"), alias="ARENA_OUTPUT_DIR")
    arena_data_retention_days: int = Field(default=1, ge=1, le=3650, alias="ARENA_DATA_RETENTION_DAYS")
    arena_sample_data_dir: Path = Field(default=Path("../data/sample"), alias="ARENA_SAMPLE_DATA_DIR")
    arena_lobster_raw_dir: Path = Field(
        default=_PROJECT_ROOT / "data/lobster",
        alias="ARENA_LOBSTER_RAW_DIR",
    )
    arena_itch_raw_dir: Path = Field(
        default=_PROJECT_ROOT / "data/nasdaq-itch",
        alias="ARENA_ITCH_RAW_DIR",
    )
    arena_historical_data_dir: Path = Field(
        default=_PROJECT_ROOT / "data/processed/lobster",
        alias="ARENA_HISTORICAL_DATA_DIR",
    )
    arena_local_batch_max_workers: int = Field(
        default=1,
        ge=1,
        le=32,
        alias="ARENA_LOCAL_BATCH_MAX_WORKERS",
    )
    java_arena_base_url: str = Field(default="http://127.0.0.1:8081", alias="JAVA_ARENA_BASE_URL")
    java_arena_timeout_seconds: float = Field(
        default=2.0,
        gt=0.0,
        le=30.0,
        alias="JAVA_ARENA_TIMEOUT_SECONDS",
    )
    arena_remote_agent_urls: str = Field(default="", alias="ARENA_REMOTE_AGENT_URLS")
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
        alias="CORS_ALLOWED_ORIGINS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def remote_agent_url_list(self) -> list[str]:
        """Runner endpoints retained for AI service health reporting only."""
        return [url.strip() for url in self.arena_remote_agent_urls.split(",") if url.strip()]

    @property
    def nebius_explain_endpoint_url(self) -> str | None:
        return self.nebius_incident_explainer_url or self.nebius_endpoint_url("/explain-event")

    @property
    def nebius_scenario_endpoint_url(self) -> str | None:
        return self.nebius_scenario_generator_url or self.nebius_endpoint_url("/generate-scenario")

    @property
    def nebius_market_abuse_scenario_endpoint_url(self) -> str | None:
        return self.nebius_market_abuse_scenario_url or self.nebius_endpoint_url("/generate-market-abuse-scenario")

    @property
    def nebius_orderbook_alert_endpoint_url(self) -> str | None:
        return self.nebius_orderbook_alert_url or self.nebius_endpoint_url("/orderbook-alert")

    @property
    def nebius_investigation_report_endpoint_url(self) -> str | None:
        return self.nebius_investigation_report_url or self.nebius_endpoint_url("/investigation-report")

    @property
    def nebius_investigation_team_endpoint_url(self) -> str | None:
        return self.nebius_investigation_team_url or self.nebius_endpoint_url("/investigation-team")

    def nebius_endpoint_url(self, path: str) -> str | None:
        if not self.nebius_endpoint_base_url:
            return None
        return f"{self.nebius_endpoint_base_url.rstrip('/')}/{path.lstrip('/')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
