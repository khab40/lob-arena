# LOB Arena

LOB Arena is an early-stage product demo for visualizing, testing, explaining, and benchmarking market-abuse detection workflows in synthetic order-book environments.

The system combines a React visual arena, a FastAPI exchange simulator, synthetic normal and red-team agents, deterministic market microstructure detectors, and Nebius serverless infrastructure. It is designed to evolve from a controlled simulation into a practical experimentation layer for surveillance engineering teams.

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

The next product step is to add near-real-time detection features:

- streaming ingestion from market-data feeds or sanitized historical replay
- low-latency feature calculation over rolling order-book windows
- detector confidence timelines with alert thresholds
- incident replay from real or replayed market intervals
- benchmark comparisons between detector versions and market regimes

## Next Step

A practical pilot would connect the arena to sanitized historical replay data, validate detector definitions with domain experts, run Nebius benchmark jobs across controlled scenarios, and define how AI-generated explanations should support analyst review.
