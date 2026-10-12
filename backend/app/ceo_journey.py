"""Authenticated prepared playback, immutable capture and durable evidence journey."""
import secrets
import time

from app.ceo_journey_evidence import (
    context_row, factual_text, hashed, pair, paired_pages, prepared, timestamp,
    verify_explanation, verify_hash, verify_snapshot,
)
from app.ceo_journey_store import ArtifactUnavailable, InvalidSelection, JourneyStore
from app.research.saved_score_io import canonical, json_value
from app.research.saved_scores import CAMPAIGN_ID, THRESHOLDS, load_campaign


class CEOJourney:
    def __init__(self, settings, artifact_roots, *, loader=load_campaign, clock=time.time):
        self.settings, self.artifact_roots, self.loader, self.clock = settings, artifact_roots, loader, clock
        self.store = JourneyStore(settings.ceo_demo_state_dir / "journey")

    def original(self):
        # The production loader always uses its independently reviewed publication pins.
        return self.loader(self.settings.research_saved_scores_dir, self.artifact_roots)

    def campaign(self):
        campaign = self.original()
        return {**campaign.catalog(), "prepared_window": prepared(campaign)}

    def rows(self, detector):
        if detector not in THRESHOLDS:
            raise LookupError()
        campaign = self.original()
        window = prepared(campaign)
        return campaign.page(window["session_id"], detector, window["offset"], window["limit"])

    def capture(self, subject, detector, target):
        if detector not in THRESHOLDS:
            raise InvalidSelection()
        campaign = self.original()
        window = prepared(campaign)
        pages = paired_pages(campaign, window)
        page = pages[detector]
        index = next((i for i, row in enumerate(page["rows"]) if row["target_id"] == target), None)
        if index is None or not page["rows"][index]["alert"]:
            raise InvalidSelection()
        identifier = secrets.token_hex(16)
        snapshot = hashed({"id": identifier, "campaign_id": CAMPAIGN_ID, "detector": detector,
            "threshold": page["threshold"], "row": page["rows"][index], "paired_scores": pair(pages, index),
            "context": [context_row(pages, i) for i in range(max(0, index - 16), index)],
            "provenance": campaign.provenance, "workspace_id": "ceo-demo", "created_at": timestamp(self.clock())},
            "snapshot_sha256")
        snapshot = json_value(canonical(snapshot))
        verify_snapshot(snapshot, identifier)
        stored = self.store.write(subject, identifier, "snapshot", snapshot)
        if canonical(stored) != canonical(snapshot):
            raise ArtifactUnavailable()
        return verify_snapshot(stored, identifier)

    def snapshot(self, subject, identifier):
        return verify_snapshot(self.store.existing(subject, identifier, "snapshot"), identifier)

    def explain(self, subject, identifier):
        snapshot = self.snapshot(subject, identifier)
        try:
            value = self.store.existing(subject, identifier, "explanation")
        except LookupError:
            value = hashed({"mode": "deterministic_fallback", "input_sha256": snapshot["snapshot_sha256"],
                "input": snapshot, "text": factual_text(snapshot), "created_at": timestamp(self.clock())},
                "explanation_sha256")
            value = self.store.write(subject, identifier, "explanation", value)
        return verify_explanation(value, snapshot)

    def record(self, subject, identifier):
        value = self.store.existing(subject, identifier, "saved")
        verify_hash(value, "record_sha256")
        if (set(value) != {"id", "snapshot", "explanation", "saved_at", "record_sha256"}
                or value["id"] != identifier or not isinstance(value["saved_at"], str)):
            raise ArtifactUnavailable()
        snapshot = verify_snapshot(value["snapshot"], identifier)
        verify_explanation(value["explanation"], snapshot)
        return value

    def save(self, subject, identifier):
        snapshot = self.snapshot(subject, identifier)
        explanation = verify_explanation(self.store.existing(subject, identifier, "explanation"), snapshot)
        try:
            value = self.record(subject, identifier)
        except LookupError:
            value = hashed({"id": identifier, "snapshot": snapshot, "explanation": explanation,
                            "saved_at": timestamp(self.clock())}, "record_sha256")
            self.store.write(subject, identifier, "saved", value)
            value = self.record(subject, identifier)
        if (canonical(value["snapshot"]) != canonical(snapshot)
                or canonical(value["explanation"]) != canonical(explanation)):
            raise ArtifactUnavailable()
        return value

    def listing(self, subject):
        records = [self.record(subject, identifier) for identifier in self.store.saved_ids(subject)]
        return [{"id": value["id"], "symbol": value["snapshot"]["row"]["symbol"],
                 "detector": value["snapshot"]["detector"], "saved_at": value["saved_at"]}
                for value in sorted(records, key=lambda item: (item["saved_at"], item["id"]), reverse=True)]
