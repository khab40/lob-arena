"""Verify or publish a retained, completed G8 release; never execute evaluation."""

import argparse
import json
from pathlib import Path

from app.ml.lightgbm.g8_publication_recovery import RecoveryBinding, resume_publication, verify_checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True, help="Independently retained seal hash")
    parser.add_argument("--binding", type=Path, required=True, help="Reviewed recovery binding, not discovered from storage")
    parser.add_argument("--publish", action="store_true", help="Resume only publication to the bound S3 result prefix")
    args = parser.parse_args()
    binding = RecoveryBinding.model_validate_json(args.binding.read_bytes())
    if args.publish:
        receipt = resume_publication(args.checkpoint, expected_sha256=args.checkpoint_sha256, binding=binding)
    else:
        verify_checkpoint(args.checkpoint, expected_sha256=args.checkpoint_sha256, binding=binding)
        receipt = {"checkpoint_verified": True, "remote_accessed": False, "checkpoint_sha256": args.checkpoint_sha256}
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
