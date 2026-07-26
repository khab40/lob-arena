# Feature-pipeline fixture

This directory contains a small, generated canonical-event fixture for the
versioned feature pipeline. It is not licensed market data.

- `fixture/events.jsonl` mixes historical background events with a synthetic
  layering overlay using the same canonical schema emitted by Java.
- `fixture/run-metadata.json` declares the instrument/session and integer-price
  semantics used to validate every row.
- `fixture/labels.json` is separate synthetic-scenario ground truth. Historical
  rows are deliberately left unlabeled outside the attack window.

Generate the reproducible Parquet dataset and quality report from the repository
root:

```bash
make generate-features FEATURE_OVERWRITE=1
```

See [Feature engineering for LightGBM](../../docs/feature-engineering-lightgbm.md)
for the schema, formulas, and train/validation split rules.
