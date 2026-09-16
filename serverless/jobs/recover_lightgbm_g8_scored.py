"""Verify a retained scored checkpoint; --log resumes only its reserved MLflow run."""
import argparse
import json
from pathlib import Path

from app.ml.lightgbm.g8_mlflow_recovery import ReservationSpec, ResumeTarget
from app.ml.lightgbm.g8_scored_checkpoint import recover_scored_checkpoint, verify_scored_checkpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--reservation", type=Path, required=True, help="Independently retained reviewed reservation")
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--log", action="store_true", help="Log-only recovery; never creates a run or scores")
    args = parser.parse_args()
    target = ResumeTarget(args.ledger_root, ReservationSpec.model_validate_json(args.reservation.read_bytes()))
    kwargs = dict(expected_sha256=args.checkpoint_sha256, target=target)
    if args.log:
        result = recover_scored_checkpoint(args.checkpoint, **kwargs)
    else:
        checkpoint = verify_scored_checkpoint(args.checkpoint, **kwargs)
        result = dict(checkpoint_sha256=args.checkpoint_sha256, mlflow_run_id=checkpoint.mlflow_run_id,
                      local_verified=True, mlflow_writes=0, scoring_invocations=0)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
