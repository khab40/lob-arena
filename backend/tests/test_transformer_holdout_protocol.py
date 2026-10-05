"""Locked planning metadata cannot drift away from the retained candidate."""
import hashlib
import json
from pathlib import Path

from app.features.pipeline import FEATURE_COLUMNS
from app.ml.transformer.settings_schema import SettingsRelease

ROOT = Path(__file__).resolve().parents[2]


def test_protocol_binds_exact_research_settings_before_any_holdout_access():
    raw = (ROOT / "configs/releases/transformer/selected-settings-20261005.json").read_bytes()
    protocol = json.loads((ROOT / "configs/experiments/transformer/c4-holdout-20261005.json").read_bytes())
    settings = SettingsRelease.model_validate_json(raw)
    assert protocol["settings_sha256"] == hashlib.sha256(raw).hexdigest() == settings.sha256()
    assert settings.preprocessing.ordered_features == FEATURE_COLUMNS
    assert protocol["candidate"]["checkpoint_sha256"] == settings.artifacts.checkpoint.sha256
    assert protocol["candidate"]["epoch"] == settings.lineage.selected_epoch
    assert protocol["fixed_thresholds"]["transformer"] == {p.mode: p.threshold for p in settings.operating_points}
    assert protocol["selected_mode"] == settings.selected_mode
    assert protocol["fitting_allowed"] is False
    assert protocol["proposed_execution"]["authorized"] is False
    assert protocol["holdout"]["inventory_verified"] is False
    assert protocol["holdout"]["global_blindness"] is False
    assert protocol["g8_g9_reopened"] is False
    assert protocol["bootstrap"]["unit"] == "whole_base_session"
    assert protocol["bootstrap"]["preserve_all_replay_variants"] is True
