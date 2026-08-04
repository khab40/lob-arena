# Market Profiles

This registry contains canonical `market_profile_v1` files selectable by the
Java Arena's `synthetic_profile` source. The filename must be
`<profile_id>.json`, and Java recomputes the embedded `profile_sha256` before
loading it.

`fixture-aapl-itch-v1.json` is derived from the repository's tiny synthetic
ITCH binary fixture. It verifies the profile contract only and must not be used
as evidence of real-market realism.

Generate real profiles locally with `scripts/build_market_profile.py` from
licensed, normalized training and disjoint held-out windows. Do not commit raw
Nasdaq sessions or derived real-market profiles/reports without the applicable
data rights and repository approval.
