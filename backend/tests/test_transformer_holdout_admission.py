import pytest

pytest.importorskip("numpy")
pytest.importorskip("cryptography")

from app.ml.transformer.holdout_supervision import supervise
from test_transformer_holdout_supervision import setup


def test_creation_and_first_observation_share_one_admission():
    req, selectors, pins, job = setup()
    clock, actions = [1000.0], []
    observations = iter([None, job(), job("COMPLETED")])
    def read(remaining):
        actions.append(("read", remaining))
        return next(observations)
    def admit(remaining):
        actions.append(("create", remaining))
        clock[0] += 85
    result = supervise(req, selectors, pins, read=read,
        deliver=lambda *args: actions.append(("context", None)), cancel=lambda _: pytest.fail("cancel"),
        emit=lambda _: None, now=lambda: clock[0], pause=lambda _: None, admit=admit)
    assert result["state"] == "COMPLETED"
    assert [name for name, _ in actions] == ["read", "create", "read", "context", "read"]
    assert actions[1][1] == 120 and actions[2][1] == 35


def test_ambiguous_create_and_delayed_visibility_never_create_again():
    req, selectors, pins, job = setup()
    clock, creates, contexts, emitted = [1000.0], [], [], []
    observations = iter([None, None, None, job(), job("COMPLETED")])
    def pause(seconds):
        clock[0] += seconds
    def admit(remaining):
        assert not emitted[-1]["admission_ready"]
        creates.append(remaining)
    result = supervise(req, selectors, pins, read=lambda _: next(observations),
        deliver=lambda c, _: contexts.append(c), cancel=lambda _: pytest.fail("cancel"),
        emit=emitted.append, now=lambda: clock[0], pause=pause, admit=admit)
    assert result["state"] == "COMPLETED" and len(creates) == len(contexts) == 1
    readiness = [value["admission_ready"] for value in emitted if value["state"] == "absent"]
    assert readiness == [True, False, False, False]


@pytest.mark.parametrize("state", ["RUNNING", "COMPLETED"])
def test_existing_job_is_never_adopted_or_cancelled(state):
    req, selectors, pins, job = setup()
    actions = []
    with pytest.raises(ValueError, match="requires an absent Job"):
        supervise(req, selectors, pins, read=lambda _: job(state), deliver=lambda *a: actions.append(a),
            cancel=actions.append, emit=actions.append, now=lambda: 1000, pause=lambda _: None, admit=actions.append)
    assert actions == []


@pytest.mark.parametrize("elapsed", [90, 91, 119])
def test_slow_absence_observation_reserves_thirty_seconds(elapsed):
    req, selectors, pins, _ = setup()
    clock, actions = [1000.0], []
    def read(remaining):
        clock[0] += elapsed
    with pytest.raises(TimeoutError, match="observation reserve"):
        supervise(req, selectors, pins, read=read, deliver=lambda *a: actions.append(a),
            cancel=actions.append, emit=lambda _: None, now=lambda: clock[0], pause=lambda _: None, admit=actions.append)
    assert actions == []


def test_ambiguous_creation_without_visibility_expires_without_retry():
    req, selectors, pins, _ = setup()
    clock, creates, actions = [1000.0], [], []
    def admit(remaining):
        creates.append(remaining)
        clock[0] += 89
    def pause(seconds):
        clock[0] += seconds
    with pytest.raises(TimeoutError):
        supervise(req, selectors, pins, read=lambda _: None, deliver=lambda *a: actions.append(a),
            cancel=actions.append, emit=lambda _: None, now=lambda: clock[0], pause=pause, admit=admit)
    assert len(creates) == 1 and actions == [] and clock[0] >= 1120
