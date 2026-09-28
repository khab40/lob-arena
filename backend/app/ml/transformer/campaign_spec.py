"""Resolved, finite first-campaign configuration; contains no model execution."""
from __future__ import annotations

from pathlib import Path

from .verification_spec import (
    INVENTORY_SHA, ROOT_SHA, SEQUENCE_SHA, TABULAR_SHA, canonical, checked_file, digest,
)


def configuration():
    """Changing this approved protocol requires a new reviewed config digest."""
    slots = [("role-audit", "cpu", 3600), ("smoke", "gpu", 3600)]
    slots += [(f"search-{size}-{lr}", "gpu", 7200)
              for size in (64, 128) for lr in ("0003", "001")]
    slots += [(f"seed-{seed}", "gpu", 7200) for seed in (7, 2027)]
    slots += [("inference", "gpu", 3600), ("calibration", "cpu", 3600)]
    return {
        "schema_version": "transformer_campaign_v1",
        "campaign_id": "transformer-c4-development-20260928-v1",
        "access_scope": "development",
        "inputs": {"inventory_sha256": INVENTORY_SHA, "root_file_sha256": ROOT_SHA,
            "tabular_sha256": TABULAR_SHA, "sequence_sha256": SEQUENCE_SHA,
            "normalization_sha256": "339e4a2b5738d4219a0fe64768e7d5babb86934cd61f2224c76c6a1b295433bc",
            "feature_release_id": "nasdaq-public-sample-v1-c4-5c85182-20260905-features",
            "feature_release_sha256": "956e5d0e600e831d662733b773f77790a649e7da6709ab88ed2294f4112a2198",
            "fold_rows": {"train": 33450, "validation": 9210},
            "sequence_length": 64, "feature_count": 60},
        "roles": {"algorithm": "canonical_source_group_sha256_round_robin_v1",
            "order": ["selection", "calibration", "operating_point"],
            "minimum_positive_rows": 20, "minimum_negative_rows": 20,
            "shared_source_observations": "merge_before_assignment",
            "insufficient_support": "block_without_reassignment"},
        "model": {"layers": 2, "widths": [64, 128], "heads": 4,
            "ffn_multiplier": 4, "dropout": 0.1, "pre_norm": True,
            "encoding": "fixed_sinusoidal", "pooling": "last_valid_token",
            "missingness": "concatenate_indicators", "target": "attack_active"},
        "training": {"optimizer": "AdamW", "learning_rates": [0.0003, 0.001],
            "weight_decay": 0.01, "betas": [0.9, 0.999], "epsilon": 1e-8,
            "gradient_clip": 1.0, "batch_size": 64, "accumulation": 1,
            "max_epochs": 30, "search_seed": 42, "confirmation_seeds": [7, 2027],
            "candidate_seed": 42, "precision": "float32", "tf32": False,
            "deterministic_algorithms": True, "warmup_fraction": 0.05,
            "schedule": "cosine", "final_lr_fraction": 0.1,
            "loss": "binary_cross_entropy_with_logits",
            "weights": "equal_class_equal_base_session_within_class_mean_one",
            "sampling": "seeded_epoch_shuffle_without_label_sampling"},
        "selection": {"metric": "unweighted_selection_log_loss", "direction": "min",
            "patience": 5, "min_delta": 1e-6, "epoch_tie": "earliest",
            "trial_ties": ["parameter_count", "canonical_config_sha256"],
            "require_complete_grid": True, "log_loss_range_max": 0.05,
            "f1_at_half_range_max": 0.05},
        "calibration": {"method": "temperature", "role": "calibration",
            "temperature_bounds": [0.05, 20.0], "max_evaluations": 200,
            "tolerance": 1e-6, "objective": "unweighted_log_loss",
            "diagnostic_role": "operating_point", "ece_equal_width_bins": 10,
            "reject_if_both_brier_ece_worsen_over": 1e-6},
        "thresholds": {"role": "operating_point", "precision_floor": 0.9,
            "recall_floor": 0.9, "rules": "existing_lightgbm_operating_points",
            "unattainable_floor": "block_freeze"},
        "resources": {"gpu": {"platform": "gpu-l40s-a", "preset": "1gpu-8vcpu-32gb"},
            "cpu": {"platform": "cpu-e2", "preset": "4vcpu-16gb"},
            "slots": [{"id": name, "kind": kind, "timeout_seconds": timeout}
                      for name, kind, timeout in slots],
            "concurrency": 1, "restart_policy": "never", "preemptible": False,
            "ephemeral_disk_gib": 100, "input_cache_gib": 8,
            "output_per_job_gib": 2, "output_total_gib": 20,
            "publication_reserve_seconds": 600, "automatic_replacement": False,
            "cost_policy": "operator_managed_alerts"},
        "mlflow": {"experiment": "lob-arena/transformer-development",
            "registered_model": "lob-arena-transformer-attack-active",
            "alias_scope": "research_only", "readback_required": True},
        "authorization": {"implementation": "approved", "execution": "separate_exact_package",
            "final_test": False, "new_permissions": "separate_approval"},
    }


def load_configuration(path: Path, expected_sha256: str):
    """Verify externally supplied file-byte SHA, then the canonical protocol."""
    import json

    value = json.loads(checked_file(path, expected_sha256))
    # Canonical comparison also rejects bool/int equivalence and unknown fields.
    if canonical(value) != canonical(configuration()):
        raise ValueError("configuration differs from the reviewed finite campaign")
    return value


def configuration_sha256():
    return digest(canonical(configuration()))
