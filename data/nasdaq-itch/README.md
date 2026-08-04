# Synthetic Nasdaq TotalView-ITCH fixture

`fixture/2026-01-02.NASDAQ_ITCH50.fixture.gz` is generated data, not a Nasdaq
session. It covers System Event and Stock Directory messages plus `A`, `F`,
`E`, `C`, `X`, `D`, and `U` visible-order transitions. It also contains one
unsupported administrative message so unsupported-message accounting is tested.

Rebuild it with:

```bash
uv run python data/nasdaq-itch/fixture/build_fixture.py
```

Place licensed or otherwise authorized length-prefixed ITCH 5.x `.gz`, `.itch`,
or `.bin` files under `data/nasdaq-itch/`. Filenames must contain a trade date
as `YYYYMMDD`, `YYYY-MM-DD`, or `MMDDYYYY`. Raw sessions remain untracked; only
this small synthetic fixture may be committed.
