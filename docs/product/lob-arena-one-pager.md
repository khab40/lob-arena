# LOB Arena

LOB Arena is an early-stage product demo for visualizing, testing, explaining, and benchmarking market-abuse detection workflows in synthetic order-book environments.

The system combines a React visual arena, a Java/Spring exchange and live runtime,
Python data/ML/AI services, synthetic agents, deterministic detectors and Nebius
Serverless Jobs. Historical LOBSTER/Nasdaq ingestion and hybrid replay already exist.

## What It Demonstrates

- A live synthetic order book with changing bids, asks, spread, mid-price, depth, and imbalance.
- Abuse-like scenarios such as spoofing-like walls, layering-like patterns, quote-stuffing bursts, and liquidity evaporation.
- Deterministic detectors that produce confidence scores and structured evidence.
- Incident review with replay context and plain-English AI explanations.
- Batch benchmark runs that compare detector precision, recall, F1, and detection latency.

## How Nebius Is Used

- **Nebius Serverless AI Endpoint** explains synthetic incidents, generates investigation summaries, and drafts bounded red-team scenario ideas.
- **Nebius Serverless AI Jobs** run offline detector tournaments, synthetic dataset generation, feature extraction, evaluation runs, and benchmark reports.

The browser never calls Nebius directly. The FastAPI backend owns endpoint URLs, tokens, request shaping, and fallback behavior.

## Why It Matters

Market surveillance concepts are difficult to evaluate because order-book data is high-volume, detector output is technical, and suspicious behavior is hard to replay. This arena creates a controlled environment where product, compliance, and engineering teams can see the same evidence, test detector behavior, and discuss explainability before deeper market-data integration.

## Product Direction

The active sequence is governed LightGBM qualification, a standalone sequence
Transformer, a Transformer-to-LightGBM cascade, integrated comparison evidence,
then a secure CEO workflow. LightGBM training/calibration and both C4 projections
exist; production G8 evaluation is open and G9 exit blocked. Transformer training,
cascade and near-real-time learned-model integration remain planned.

Live rules already produce confidence timelines and incidents. Learned models
will first be compared on historical/synthetic/hybrid replay, then considered
for controlled shadow serving with causal features and a verified fallback.
Customer feed/detector adapter productization remains parked.

## Next Step

Complete the gated LightGBM evaluation and signed exit before advancing the
learned-detector sequence. See [current roadmap evidence](../roadmap/CURRENT_STATUS.md)
and the [serving use cases](../use-cases/ml-model-serving.md). No production
market-abuse detection or compliance acceptance is claimed.
