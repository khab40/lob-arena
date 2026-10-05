"""Separate inference request; metadata alone never grants final access."""
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, StrictInt, model_validator

from .contracts import Digest
from .settings_schema import Artifact, SettingsRecord

SETTINGS_SHA = "2efbed46a82470d86107886041c5eab05265aa89c390f10bce557a9c838b05ab"
PROTOCOL_SHA = "9ca25496c6c1ca82f7bed064e291060b334ab510c0c7c4571230360ab3f2639e"
OUTPUT_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
OUTPUT_ROOT = "campaigns/wave1-research-20260816/transformer-holdout/"
G8_PREFIX = ("s3://" + OUTPUT_BUCKET + "/campaigns/nasdaq-g6-development-20260907/"
             "final/nasdaq-g8-replacement-r5-20260917/")
MAX_OUTPUT = 2 * 1024**3
MAX_READ = 16 * 1024**3


class InputObject(SettingsRecord):
    path: str
    scope: Literal["development", "final_test"]
    reference: Artifact

    @model_validator(mode="after")
    def safe_path(self):
        path = PurePosixPath(self.path)
        if (path.is_absolute() or str(path) != self.path or ".." in path.parts
                or not path.parts or "%" in self.path or "\\" in self.path
                or any(c.isspace() for c in self.path)
                or not self.reference.uri.startswith("s3://")):
            raise ValueError("plain relative input path and exact S3 reference required")
        return self


class HoldoutRequest(SettingsRecord):
    schema_version: Literal["transformer_holdout_request_v1"] = "transformer_holdout_request_v1"
    run_id: Annotated[str, Field(pattern=r"^transformer-holdout-[a-z0-9-]{1,40}$")]
    source_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    image_repository: Annotated[str, Field(pattern=r"^cr\.eu-north1\.nebius\.cloud/[a-z0-9]+/[a-z0-9-]+$", max_length=64)]
    image_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    context_public_key: Digest
    nonce: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    settings_sha256: Literal[SETTINGS_SHA] = SETTINGS_SHA
    protocol_sha256: Literal[PROTOCOL_SHA] = PROTOCOL_SHA
    package_sha256: Digest
    provider_spec_sha256: Digest
    inputs: tuple[InputObject, ...] = Field(min_length=3, max_length=256)
    tabular_path: str
    sequence_path: str
    baseline_paths: tuple[str, ...] = Field(min_length=1, max_length=30)
    reference_logits_path: str
    reference_targets_sha256: Digest
    reference_rows: Annotated[StrictInt, Field(ge=1, le=64)]
    output_bucket: Literal[OUTPUT_BUCKET] = OUTPUT_BUCKET
    output_prefix: str
    timeout_seconds: Literal[3600] = 3600
    startup_seconds: Literal[600] = 600
    create_to_terminal_seconds: Literal[7200] = 7200
    batch_size: Literal[64] = 64
    jobs: Literal[1] = 1
    restart: Literal["never"] = "never"
    fitting: Literal[False] = False
    reference_atol: Literal[1e-5] = 1e-5
    reference_rtol: Literal[1e-6] = 1e-6

    @model_validator(mode="after")
    def inventory(self):
        paths = {item.path: item for item in self.inputs}
        uris = [item.reference.uri for item in self.inputs]
        if len(paths) != len(self.inputs) or len(set(uris)) != len(uris):
            raise ValueError("duplicate input paths or object identities")
        if sum(item.reference.size_bytes for item in self.inputs) > MAX_READ:
            raise ValueError("input envelope exceeds read budget")
        final = (self.tabular_path, self.sequence_path, *self.baseline_paths)
        if (len(set(final)) != len(final) or any(p not in paths for p in final)
                or any(paths[p].scope != "final_test" for p in final)
                or self.reference_logits_path not in paths
                or paths[self.reference_logits_path].scope != "development"):
            raise ValueError("final and parity inputs must have distinct declared scopes")
        if any(not paths[p].reference.uri.startswith(G8_PREFIX) for p in self.baseline_paths):
            raise ValueError("baseline must reuse original G8 publication")
        if self.output_prefix != OUTPUT_ROOT + self.run_id + "/":
            raise ValueError("holdout output identity differs")
        return self

    def input(self, path):
        return next(item for item in self.inputs if item.path == path)


def object_location(reference):
    parts = urlsplit(reference.uri)
    return parts.netloc, parts.path[1:]
