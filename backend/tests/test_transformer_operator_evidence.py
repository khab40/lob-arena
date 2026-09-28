"""Fresh checkouts must retain the exact approved orchestration bytes."""
import json
from pathlib import Path

import pytest

from app.ml.transformer.verification_spec import checked_file

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/evidence"


def test_preserved_operator_matches_immutable_proposal_and_rejects_change(tmp_path):
    proposal = json.loads((EVIDENCE / "transformer-development-replacement-r2-20260928.json").read_bytes())
    path = EVIDENCE / "transformer-development-r2-operator-20260928.py"
    expected = proposal["operator_helper_sha256"]
    payload = checked_file(path, expected)
    compile(payload, str(path), "exec")  # Parse only; never execute credential or cloud operations.
    changed = tmp_path / "changed-helper.py"
    changed.write_bytes(payload + b"\n# changed\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        checked_file(changed, expected)
