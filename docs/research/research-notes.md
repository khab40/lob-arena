# Research Notes

The project draws from public research on agent-based market simulation, limit order book realism, and synthetic abuse-like behavior.

## Core References

- ABIDES: Towards High-Fidelity Market Simulation for AI Research.
- Spoofing the Limit Order Book: An Agent-Based Model.
- Get Real: Realism Metrics for Robust Limit Order Book Market Simulations.
- Learning to simulate realistic limit order book markets from data as a World Agent.
- TRADES: Generating Realistic Market Simulations with Diffusion Models.

See `assets/articles/README.md`, `assets/articles/metadata.json`, and `assets/articles/references.bib` for source metadata.

## Positioning

The arena should be described as a synthetic research and education tool. Claims should focus on visualization, repeatable benchmarks, and explanation workflows rather than production surveillance guarantees.

## Historical research directions from ARD-0001

These are exploratory ideas, not approved roadmap commitments or implemented capabilities.

The broader modeling direction is to treat the exchange as one example of a multidimensional time-series process. The same architecture could model not only quotes, trades, spreads, depth, and order-flow events, but also synchronized external context such as news, macro events, political statements, social signals, or other exogenous shocks.

This opens several future research and product directions:

- digital twin of a market process: run the real or historical process and a virtual mathematical version side by side, using differences between them to improve models and predictions
- adversarial behavior modeling: represent market participants as agents or groups of agents with conflicting goals, strategies, and observable consequences
- semantic attack simulation: model not only order-book abuse, but also misinformation, data poisoning, fake signals, deepfake-driven market narratives, and other context-level attacks
- online learning loop: continuously validate predictions, detector outputs, and decisions against the simulated or replayed process, then refine the model
- Boyd-cycle framing: model both attacker and defender loops of observe, orient, decide, and act, making the arena a conflict simulation rather than a passive dashboard
- cross-domain extension: use the same simulation pattern for other complex adversarial systems where multiple entities interact over time, such as competitive markets, information operations, supply chains, or social tension modeling

The exchange domain is a strong first case study because it has rich public data, clear event streams, measurable outcomes, visible agent behavior, and well-known market microstructure indicators. A convincing prototype here can become the foundation for a broader platform for simulation, prediction, and decision support in adversarial multidimensional systems.
