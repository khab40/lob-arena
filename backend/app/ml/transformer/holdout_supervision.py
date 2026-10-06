"""Observe one approved identity, deliver context once and enforce its accounting bound."""
from datetime import datetime
import time

from .holdout_delivery import context_for_job
from .role_execution_context import LIVE_STATES

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "CANCELED"}


def supervise(request, selectors, pins, *, read, deliver, cancel, emit,
              now=time.time, pause=time.sleep):
    started, identity, delivered, cancel_started = now(), None, False, False
    owned_live = False
    cancel_at, stop_at = None, started + 120
    try:
        while True:
            job = read()
            checked = now()
            if job is None:
                if identity or checked >= stop_at:
                    raise TimeoutError("Job absent outside admission window")
                emit({"state": "absent", "observed_at": checked, "admission_ready": True})
                pause(5)
                continue
            state = job["status"]["state"]
            if state not in LIVE_STATES | TERMINAL:
                raise ValueError("unknown provider state")
            # Terminal observations never create a signature. Validate the same
            # ordinary spec through the existing live-state validator only.
            ordinary = {**job, "status": {**job["status"], "state": "RUNNING"}}
            context = context_for_job(ordinary, request, selectors, **pins)
            if identity and identity != context["job_id"]:
                raise ValueError("Job identity changed")
            created = datetime.fromisoformat(job["metadata"]["created_at"].replace("Z", "+00:00")).timestamp()
            if created > checked + 5:
                raise ValueError("provider accounting observation outside bound")
            identity = context["job_id"]
            owned_live = state in LIVE_STATES
            if checked - created > request.create_to_terminal_seconds:
                raise ValueError("provider accounting observation outside bound")
            stop_at = created + request.create_to_terminal_seconds
            cancel_at = stop_at - 120  # Reserve cancellation/readback time.
            emit({"state": state, "job_id": identity, "observed_at": checked,
                  "admission_ready": False, "created_at": created, "context_delivered": delivered})
            if state in TERMINAL:
                return {"state": state, "job_id": identity, "context_delivered": delivered}
            if checked >= cancel_at:
                if not cancel_started:
                    cancel_started = True  # Ambiguous cancellation is never retried.
                    cancel(identity)
                if now() >= stop_at:
                    raise TimeoutError("operator must reconcile terminal state")
            elif not delivered:
                # Sign the actual live observation, not the terminal-validation copy.
                deliver(context_for_job(job, request, selectors, **pins))
                delivered = True
            pause(min(10, max(0, stop_at - now())))
    except Exception:
        if identity and owned_live and not cancel_started:
            cancel_started = True
            cancel(identity)
        raise
