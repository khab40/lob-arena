# LightGBM and Transformers: data, training, evidence and detection

Research status reconciled on 8 October 2026; [current status](roadmap/CURRENT_STATUS.md) owns remaining acceptance.

Related work: [LightGBM #23](https://github.com/khab40/lob-arena/issues/23),
[Transformer #24](https://github.com/khab40/lob-arena/issues/24),
[combined model #25](https://github.com/khab40/lob-arena/issues/25),
[GitHub Project #3](https://github.com/users/khab40/projects/3).

**We are building a system that tests market-abuse detectors against the same reproducible market scenarios, then retains the models that show measurable value.** LightGBM is our completed research baseline. The frozen Transformer has completed independently verified training, comparison and authorized December evaluation. The operator chose bounded continuation; combined-model and live integration remain future work. Production performance is not established.

## 1. Our data: real market activity with controlled attacks

Our current dataset uses public **Nasdaq TotalView-ITCH order-event data** for **AAPL, MSFT and NVDA**. We download the complete daily files, then retain **10:00–10:30 Eastern Time** and reconstruct the visible order book to ten price levels.

We replay each selected market session unchanged, then create nine additional versions with controlled examples of:

- **Spoofing-like walls:** large displayed orders intended to create misleading supply or demand.
- **Layering:** misleading orders distributed across several price levels.
- **Quote stuffing:** bursts of order activity.

Each attack type uses three random seeds, providing repeatable variations. Four dates × three stocks give **12 base sessions and 120 replay streams**.

This gives us real market background and known attack timing. However, **the attacks are synthetic, and unchanged historical periods are assumed research controls—not independently proven abuse-free periods**. Licensed LOBSTER and independently reviewed client data are supported directions for stronger validation. [Data preparation](use-cases/ml-data-preparation.md)

## 2. Why several dates, and how we separate learning from testing

Adjacent market observations are highly similar. Randomly mixing them between training and testing could let a model effectively recognise something it has already seen. We therefore learn from earlier dates and evaluate on later dates.

| Purpose | Exact dates | What happens |
| --- | --- | --- |
| Training | **30 January and 27 March 2019** | Learn model parameters |
| Validation and calibration | **30 October 2019** | Select configuration, adjust probabilities and choose alert thresholds |
| Final detection evaluation | **30 December 2019** | Measure the frozen model on withheld observations |

These are the four public-source dates frozen into our current research contract. Their separation exposes models to different sessions, but **four dates do not demonstrate coverage of all market conditions**. Earlier seven-date plans should not be confused with the dataset actually evaluated.

A session’s original replay and every attack variant stay in the same partition. Features use only information available at the prediction time; boundary rules prevent overlapping feature history from leaking across partitions. Development and final-test data also have separate access controls.

Our first LightGBM campaign reused October’s validation data for model selection, calibration and threshold selection. That is a limitation. The completed Transformer campaign separates selection (NVDA), calibration (MSFT) and operating-point selection (AAPL) within October validation. One date and one instrument per role still limit generalization.

December was unseen by the frozen Transformer but already evaluated by LightGBM. Its separately authorized Transformer holdout is verified; **future independent qualification needs fresh untouched data and an appropriate protocol**. This is not a globally blind benchmark.

## 3. How we prepare the data and train each algorithm

First, we validate order events, reconstruct the order book and replay events chronologically. We calculate **60 numerical features**, including order-flow, cancellation, liquidity and book-shape measurements, using the top five price levels and trailing **2-second and 10-second windows**. Labels are attached afterwards, keeping the answers out of feature calculation.

**LightGBM learns combinations of numerical signals.** It builds decision trees sequentially, with later trees correcting remaining prediction errors. For example, it can learn that a cancellation burst is more suspicious when accompanied by a particular liquidity pattern. [LightGBM documentation](https://lightgbm.readthedocs.io/)

Our implementation trains a binary **“attack active?”** classifier on CPU. It balances contributions from classes and base sessions, compares a bounded set of configurations, stops training based on validation performance and checks different random seeds. The selected model uses **31 of the 60 features**.

We then apply **isotonic calibration**: a learned mapping that makes model scores better reflect observed attack frequencies. Finally, we freeze an alert threshold. The selected balanced threshold is approximately **0.577**; it was chosen to maximise validation F1, not because that number has an inherent market meaning. [Training and calibration](use-cases/ml-training-selection.md)

**The Transformer learns patterns across a sequence.** Attention lets it relate different positions in that sequence—for example, an order build-up followed by cancellation and liquidity changes. [Original Transformer paper](https://arxiv.org/abs/1706.03762)

Our prepared input contains **up to 64 consecutive retained feature rows**, each with 60 features. These are numerical market histories, not text or raw exchange-message tokens. Normalisation is fitted only on training data; padding, missing values and future-information exclusion are checked.

The completed GPU campaign compared two widths and two learning rates, verified three-seed stability, and retained width 128 / learning rate 0.0003 / seed 42 / epoch 4. Temperature was fitted only on the calibration role; thresholds were frozen before December access. [Model design and selection](architecture/ARD-0036-market-sequence-transformer.md), [verified holdout](ml/transformer-holdout-report-20261007.md).

## 4. How we prove what produced a result

Every result should be traceable through:

**Source data → replay and labels → features and split → model and calibration → predictions and metrics.**

We retain:

- **SHA-256 fingerprints:** identify exact source files, datasets, configurations, model weights and outputs; changed bytes produce a different fingerprint.
- **Versioned manifests and row identities:** specify precisely which observations and artifacts belong to a run.
- **Code commit, container-image digest, seeds and cloud Job identity:** identify the execution environment.
- **Signed decisions and independent artifact readback:** connect results to retained evidence. LightGBM has verified MLflow records; Transformer online MLflow reconciliation remains open.

For the completed LightGBM evaluation, an independent process checked **176 published objects**, their hashes and sizes, and the recorded metrics.

**Hashes prove artifact identity and integrity. They do not prove that labels are correct or that a model works in production.** Those require separate validation.

## 5. How detection will work in real time

The intended live path is:

**Exchange events → updated order book → causal features → trained model → calibrated score → threshold → evidence-backed alert.**

Training happens separately. The running detector applies frozen parameters to new observations; it does not retrain for every event.

LightGBM can make the numerical decision on CPU. The research Transformer consumes recent feature history; a dedicated inference adapter and causal event integration still need implementation and validation. The immediate demo plays verified saved scores, without fresh model execution. [Continuation scope](ml/transformer-research-disposition-20261008.md).

Our proposed combination feeds **Transformer-derived signals plus the existing numerical features into a new LightGBM model**. This lets LightGBM learn when temporal context adds useful information. Training must prevent the Transformer from supplying memorised answers for downstream training rows.

The combination must beat the standalone models sufficiently to justify its latency and GPU cost. The planned fallback for missing or stale Transformer inputs is the verified standalone LightGBM path. Live-feed integration, production latency and combined-model benefit still need validation. [Combined-model design](architecture/ARD-0037-transformer-to-lightgbm-cascade.md)

## 6. How we measure success—and what we can tell investors

Three basic measures answer different questions:

- **Precision:** of the observations flagged, how many were labelled attacks?
- **Recall:** of the labelled attack observations, how many did we catch?
- **F1:** how well do precision and recall balance?

We also need attack-level coverage, false-alert burden, detection delay, performance by attack family, probability reliability, throughput and operating cost.

On the same 15,160 December research rows / 135 positives, frozen balanced operating points produced:

| Measure | LightGBM | Existing Rules baseline |
| --- | ---: | ---: |
| Precision | **85.58%** | 0.89% |
| Recall | **65.93%** | 100% |
| F1 | **74.48%** | 1.77% |
| False-positive observations | **15** | 14,985 |
| Attack campaigns detected at least once | **27/27** | 27/27 |

LightGBM reduced false-positive **observations** by **99.90% against our existing Rules baseline**, while missing 46 of 135 positive observations. Catching every campaign once does not mean catching every attack phase or detecting it early enough. These are research measurements on one date, with synthetic positives—not production alert statistics. [Final evaluation evidence](operations/g8/g8-final-results-20260923.md)

Our defensible advantage is **repeatable, evidence-backed comparison**: identical market observations, controlled attacks, explicit trade-offs and traceable results. We have demonstrated improvement over our own Rules baseline. We have not demonstrated superiority over commercial surveillance products, and Transformer gains remain a hypothesis.

For investors: **“LOB Arena gives teams a reproducible way to test surveillance models before deployment. Our first learned detector substantially reduced false-positive observations in a controlled benchmark; the next stage tests whether temporal modelling improves detection without unacceptable cost or delay.”**
