"""Save a new local parity artifact from verified retained development logits."""
import argparse
import json
from pathlib import Path

from app.ml.transformer.holdout_reference import MAX_METADATA, prepare_reference
from app.ml.transformer.verification_spec import canonical


def prepare(settings, verification, predictions, output):
    def bounded(path, limit):
        with Path(path).open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("local reference input exceeds read bound")
        return raw

    raw, receipt = prepare_reference(bounded(settings, 65536), bounded(verification, MAX_METADATA),
                                     bounded(predictions, MAX_METADATA))
    output = Path(output)
    output.mkdir(exist_ok=False)  # Preserve any earlier preparation, including symlink destinations.
    (output / "reference-logits.json").write_bytes(raw)
    (output / "receipt.json").write_bytes(canonical(receipt))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("settings", "verification", "predictions", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(prepare(**vars(parser.parse_args())), sort_keys=True))
