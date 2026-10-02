import copy
from pathlib import Path
import subprocess
import sys

import pytest

from app.ml.transformer import role_execution_spec as spec


def request():
    return spec.request_template("1" * 40, "sha256:" + "2" * 64, "3" * 64, "4" * 32)


def test_new_slot_preserves_frozen_inputs_without_reusing_consumed_authority():
    from app.ml.transformer.verification_spec import RUN_ID as consumed

    value = request()
    spec.validate_request(value, "1" * 40)
    assert value["run_id"] != consumed
    assert value["output_prefix"].endswith(value["run_id"] + "/")
    assert value["resources"]["input_get_attempts"] == 185
    assert value["resources"]["job_count"] == 1
    assert "execution_authorized" not in value


@pytest.mark.parametrize("key", tuple(request()))
def test_every_request_field_is_bound(key):
    value = request()
    value[key] = None
    with pytest.raises(ValueError):
        spec.validate_request(value, "1" * 40)


@pytest.mark.parametrize("key", tuple(spec.resources()))
def test_resource_limits_cannot_change(key):
    value = request()
    value["resources"][key] = None
    with pytest.raises(ValueError):
        spec.validate_request(value, "1" * 40)


@pytest.mark.parametrize("alteration", ["old_schema", "unknown", "source", "bool", "secret", "version"])
def test_old_or_expanded_requests_are_rejected(alteration):
    value = request()
    if alteration == "old_schema":
        value["schema_version"] = "transformer_input_execution_v1"
    elif alteration == "unknown":
        value["approved"] = True
    elif alteration == "source":
        value["source_commit"] = "5" * 40
    elif alteration == "bool":
        value["resources"]["concurrency"] = True
    else:
        selector = value["secret_selectors"]["AWS_ACCESS_KEY_ID"]
        selector["secret_id" if alteration == "secret" else "version_id"] = "other"
    with pytest.raises(ValueError):
        spec.validate_request(value, "1" * 40)


def test_templates_do_not_share_mutable_bounds():
    changed = copy.deepcopy(request())
    changed["resources"]["mounts"].append("other")
    assert request()["resources"]["mounts"] == []


def test_envelope_imports_without_site_packages():
    backend = Path(__file__).resolve().parents[1]
    script = ("import sys; from app.ml.transformer.role_execution_spec import request_template; "
              "from app.ml.transformer.role_execution_context import context_for_job; "
              "assert 'numpy' not in sys.modules; assert 'botocore' not in sys.modules")
    subprocess.run([sys.executable, "-S", "-c", script], cwd=backend, check=True)
