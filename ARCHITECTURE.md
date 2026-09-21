# LOB Arena architecture

The maintained system design is [docs/architecture.md](docs/architecture.md).
Java owns the exchange and canonical replay stream; Python owns ingestion,
features, model development and cloud orchestration. MLflow indexes evidence;
checksummed, signed release contracts remain the authority.

## ML workflow

- [Lifecycle and implementation status](docs/use-cases/ml-lifecycle.md)
- [Data sources, labels, chronological partitions and storage](docs/use-cases/ml-data-preparation.md)
- [Training, checkpoints, calibration and hyperparameter selection](docs/use-cases/ml-training-selection.md)
- [MLflow candidates, model comparisons and planned near-real-time serving](docs/use-cases/ml-model-serving.md)
- [Architecture records](docs/architecture/README.md) and [ML review findings](docs/architecture/ml-documentation-review-20260921.md)

LightGBM development and verified scoring are implemented. C4 has tabular and
sequence projections, but Transformer training, the cascade, automatic model
promotion and live learned-detector integration remain planned. Native synthetic
recovery is verified; production G8 evaluation and the G9 exit disposition
remain open. Consult the detailed documents for evidence and authorization gates.
