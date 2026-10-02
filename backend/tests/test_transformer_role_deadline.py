import signal
import time

import pytest

from app.ml.transformer.role_deadline import deadline


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), True])
def test_invalid_deadline_does_not_change_alarm(seconds):
    handler = signal.getsignal(signal.SIGALRM)
    with pytest.raises(ValueError, match="finite and positive"):
        with deadline(seconds):
            pytest.fail("invalid deadline entered")
    assert signal.getsignal(signal.SIGALRM) == handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def test_larger_inner_limit_preserves_earlier_parent_expiry():
    handler = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError, match="deadline"):
        with deadline(0.03) as outer_end:
            with deadline(5) as inner_end:
                assert inner_end <= outer_end
                time.sleep(0.15)
    assert signal.getsignal(signal.SIGALRM) == handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def test_successful_inner_exit_restores_remaining_parent_time():
    with pytest.raises(TimeoutError, match="deadline"):
        with deadline(0.06):
            with deadline(0.01):
                pass
            remaining, interval = signal.getitimer(signal.ITIMER_REAL)
            assert 0 < remaining <= 0.06 and interval == 0
            time.sleep(0.15)


def test_catching_inner_timeout_does_not_disable_parent():
    with pytest.raises(TimeoutError, match="deadline"):
        with deadline(0.08):
            with pytest.raises(TimeoutError):
                with deadline(0.01):
                    time.sleep(0.03)
            time.sleep(0.15)
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def test_swallowed_expired_parent_still_fails_outer_exit_without_alarm_race():
    handler = signal.getsignal(signal.SIGALRM)
    for _ in range(30):
        with pytest.raises(TimeoutError, match="deadline"):
            with deadline(0.001):
                with pytest.raises(TimeoutError):
                    with deadline(1):
                        time.sleep(0.005)
                with pytest.raises(TimeoutError):
                    with deadline(1):
                        pytest.fail("expired parent must fail before entering")
        assert signal.getsignal(signal.SIGALRM) == handler
        assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def test_external_alarm_is_preserved_after_phase():
    original = signal.getsignal(signal.SIGALRM)
    def external(*_):
        raise TimeoutError("external timer")
    signal.signal(signal.SIGALRM, external)
    signal.setitimer(signal.ITIMER_REAL, 0.06)
    try:
        with deadline(0.01):
            pass
        assert signal.getsignal(signal.SIGALRM) == external
        with pytest.raises(TimeoutError, match="external timer"):
            time.sleep(0.15)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original)
