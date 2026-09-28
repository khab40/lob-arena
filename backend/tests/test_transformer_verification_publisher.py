from datetime import datetime, timedelta, UTC
import io
import json

import pytest

pytest.importorskip("numpy")
from app.ml.transformer.verification_publisher import PROJECT, deliver  # noqa: E402
from app.ml.transformer.verification_spec import RUN_ID, canonical  # noqa: E402
from test_transformer_verification_runner import request_and_key  # noqa: E402


class Absent(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


@pytest.mark.parametrize("fault", [None, "image", "job", "project", "terminal", "old", "request", "failed_marker"])
def test_armed_publisher_delivers_only_live_matching_context(fault):
    request, key = request_and_key()
    now = datetime.now(UTC)
    job = {"metadata": {"id": "aijob-fixture", "name": RUN_ID, "parent_id": PROJECT},
        "spec": {"image": "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/ti@" + request["image_digest"],
            "platform": "cpu-d3", "preset": "4vcpu-16gb", "timeout": "3600s",
            "disk": {"size_bytes": "107374182400"}}, "status": {"state": "RUNNING"}}
    if fault == "image":
        job["spec"]["image"] = "other"
    if fault == "job":
        job["metadata"]["name"] = "other"
    if fault == "project":
        job["metadata"]["parent_id"] = "other"
    if fault == "terminal":
        job["status"]["state"] = "FAILED"
    writes = []
    class Store:
        def get_object(self, **kwargs):
            raw = b"{}" if fault == "request" else canonical(request)
            return {"ContentLength": len(raw), "Body": io.BytesIO(raw),
                "LastModified": now - timedelta(seconds=240 if fault == "old" else 2)}
        def head_object(self, **kwargs):
            if fault == "failed_marker":
                return {}
            raise Absent()
        def put_object(self, **kwargs):
            writes.append(kwargs)
            return {"VersionId": "1"}
    pending = iter((None, job))
    pauses = []
    if fault:
        with pytest.raises(ValueError):
            deliver(Store(), request, key, lambda: next(pending), now=lambda: now, pause=pauses.append)
        assert writes == []
    else:
        result = deliver(Store(), request, key, lambda: next(pending), now=lambda: now, pause=pauses.append)
        assert result["envelope"]["context"]["job_id"] == "aijob-fixture"
        assert len(writes) == 1 and writes[0]["IfNoneMatch"] == "*"
    assert pauses == [5]


def test_context_timeout_records_stage_without_downloading(tmp_path, monkeypatch):
    import app.ml.transformer.verification_runner as runner
    from test_transformer_verification_transport import INVENTORY, Store
    request, _ = request_and_key()
    def timeout(*_):
        raise TimeoutError()
    monkeypatch.setattr(runner, "wait_context", timeout)
    monkeypatch.setattr(runner, "download", lambda *_: pytest.fail("download reached"))
    store = Store()
    with pytest.raises(TimeoutError):
        runner.execute(store, request, INVENTORY, "1" * 40, tmp_path / "work")
    assert json.loads(store.puts[-1]["Body"])["stage"] == "context"
