import asyncio
import json
from urllib import error, parse, request

from app.metrics import PrometheusTextRegistry, Timer
from app.schemas.arena import ArenaMetricsSnapshot, ArenaState, AttackTrackerState, ExchangeEventReplay, Incident


class JavaArenaClient:
    """Thin retained-Python adapter to the Java-owned live arena."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 2.0,
        metrics: PrometheusTextRegistry | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.metrics = metrics

    @property
    def state(self) -> ArenaState:
        return ArenaState.model_validate(self._request("GET", "/api/arena/state"))

    async def get_state(self) -> ArenaState:
        return await asyncio.to_thread(lambda: self.state)

    async def get_metrics_snapshot(self) -> ArenaMetricsSnapshot:
        payload = await asyncio.to_thread(self._request, "GET", "/api/arena/metrics-state")
        return ArenaMetricsSnapshot.model_validate(payload)

    async def start(self) -> ArenaState:
        return await self._arena_state("/api/simulation/start")

    async def pause(self) -> ArenaState:
        return await self._arena_state("/api/simulation/pause")

    async def reset(self) -> ArenaState:
        return await self._arena_state("/api/simulation/reset")

    async def stop(self) -> None:
        return None

    async def start_scenario(self, scenario_name: str) -> AttackTrackerState:
        payload = await asyncio.to_thread(
            self._request,
            "POST",
            f"/api/scenarios/{_scenario_path(scenario_name)}",
        )
        return AttackTrackerState.model_validate(payload)

    def launch_scenario(self, scenario_name: str) -> dict[str, object]:
        try:
            payload = self._request("POST", f"/api/scenarios/{_scenario_path(scenario_name)}")
        except ValueError as exc:
            return {"accepted": False, "error": str(exc)}
        return {"accepted": True, "scenario": payload}

    async def _advance_tick_async(self, running: bool = True) -> None:
        del running
        await asyncio.to_thread(self._request, "POST", "/internal/arena/step")

    async def list_incidents(self) -> list[Incident]:
        payload = await asyncio.to_thread(self._request, "GET", "/api/incidents")
        return [Incident.model_validate(item) for item in payload]

    async def get_incident(self, incident_id: str) -> Incident | None:
        try:
            payload = await asyncio.to_thread(
                self._request,
                "GET",
                f"/api/incidents/{parse.quote(incident_id, safe='')}",
            )
        except LookupError:
            return None
        return Incident.model_validate(payload)

    async def replay_exchange_events(
        self,
        *,
        after_sequence: int = 0,
        limit: int = 100,
        stream_id: str | None = None,
    ) -> ExchangeEventReplay:
        parameters: dict[str, object] = {
            "afterSequence": after_sequence,
            "limit": limit,
        }
        if stream_id is not None:
            parameters["streamId"] = stream_id
        query = parse.urlencode(parameters)
        payload = await asyncio.to_thread(
            self._request,
            "GET",
            f"/api/arena/exchange-events?{query}",
        )
        return ExchangeEventReplay.model_validate(payload)

    async def _arena_state(self, path: str) -> ArenaState:
        payload = await asyncio.to_thread(self._request, "POST", path)
        return ArenaState.model_validate(payload)

    def _request(self, method: str, path: str) -> object:
        req = request.Request(
            f"{self.base_url}{path}",
            method=method,
            headers={"Accept": "application/json"},
        )
        timer = Timer()
        outcome = "completed"
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            outcome = f"http_{exc.code}"
            if exc.code == 404:
                raise LookupError(path) from exc
            raise ValueError(f"Java arena returned HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError) as exc:
            outcome = "unavailable"
            raise RuntimeError(f"Java arena is unavailable at {self.base_url}") from exc
        finally:
            if self.metrics is not None:
                endpoint = _endpoint_label(path)
                self.metrics.inc("backend_java_arena_requests_total", method=method, endpoint=endpoint, outcome=outcome)
                self.metrics.observe(
                    "backend_java_arena_request_duration_seconds",
                    timer.elapsed(),
                    method=method,
                    endpoint=endpoint,
                    outcome=outcome,
                )


def _scenario_path(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    mapping = {
        "spoofing_like_wall": "spoofing-like",
        "layering_like": "layering-like",
        "quote_stuffing": "quote-stuffing",
        "liquidity_evaporation": "liquidity-evaporation",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {value}") from exc


def _endpoint_label(path: str) -> str:
    base = path.split("?", 1)[0]
    if base.startswith("/api/incidents/"):
        return "/api/incidents/{id}"
    return base
