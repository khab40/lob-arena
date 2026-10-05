"""Pair immutable G8 prediction rows; no LightGBM import or scoring."""
import numpy as np

from app.market_data.projections import supervised_row_id
from .verification_spec import digest


def pair_saved_predictions(dataset, prediction_rows):
    ledger = tuple(dataset.ledger())
    saved = tuple(prediction_rows)
    if len(saved) != len(ledger) or not saved:
        raise ValueError("saved baseline population differs")
    shards = {s.run_id: s for s in dataset.tabular.shards}
    seen, probabilities, families, symbols = set(), [], [], []
    for target, row in zip(ledger, saved, strict=True):
        run = row["run_id"]
        shard = shards.get(run)
        if (shard is None or row["fold"] != "test" or type(row["sequence"]) is not int
                or type(row["prediction_timestamp_ns"]) is not int
                or type(row["label"]) is not int or row["label"] not in (0, 1)):
            raise ValueError("invalid baseline fold, run, label or timestamp")
        legacy = digest(f'{run}|{row["prediction_timestamp_ns"]}|{row["sequence"]}'.encode())
        governed = supervised_row_id(root_sha256=dataset.root.canonical_hash(),
            assignment_sha256=dataset.root.assignment_sha256,
            replay_sha256=shard.replay_manifest_sha256, run_id=run,
            sequence=row["sequence"], timestamp_ns=row["prediction_timestamp_ns"])
        if (row["prediction_row_id"] != legacy or governed in seen
                or governed != target["target_id"] or row["label"] != target["label"]
                or run != target["run_id"] or row["base_session_id"] != target["base_session_id"]
                or row["campaign_id"] != target["campaign_id"]
                or row["prediction_timestamp_ns"] != target["prediction_timestamp_ns"]):
            raise ValueError("baseline identity, order or label differs")
        seen.add(governed)
        probability = row["calibrated_probability"]
        if (type(probability) not in (float, int) or not np.isfinite(probability)
                or not 0 <= probability <= 1):
            raise ValueError("original calibrated G8 probability required")
        families.append(row["attack_family"] or "control")
        symbols.append(row["instrument"])
        probabilities.append(float(probability))
    return ledger, np.asarray(probabilities), tuple(families), tuple(symbols)
