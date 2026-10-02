"""Research-fork numerical policy; no model, cloud or tracking dependency."""
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class Trial:
    width: int
    learning_rate: float
    seed: int = 42
    max_epochs: int = 30
    batch_size: int = 64
    patience: int = 5

    def __post_init__(self):
        if (self.width not in (64, 128) or self.learning_rate not in (0.0003, 0.001)
                or self.seed not in (42, 7, 2027) or self.max_epochs != 30
                or self.batch_size != 64 or self.patience != 5):
            raise ValueError("trial escaped the approved fixed research grid")

    def sha256(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def class_session_weights(labels, sessions):
    """Equal class mass, then equal base-session mass within each class."""
    if len(labels) != len(sessions) or not labels:
        raise ValueError("nonempty aligned training labels and sessions required")
    if any(type(y) is not int or y not in (0, 1) for y in labels) or set(labels) != {0, 1}:
        raise ValueError("both binary training classes required")
    if any(not isinstance(s, str) or not s for s in sessions):
        raise ValueError("bound base-session identifiers required")
    cells = Counter(zip(labels, sessions, strict=True))
    counts = {y: len({s for label, s in cells if label == y}) for y in (0, 1)}
    return [len(labels) / (2 * counts[y] * cells[y, s]) for y, s in zip(labels, sessions, strict=True)]


def learning_rate_factor(step, total_steps):
    if type(step) is not int or type(total_steps) is not int or not 0 <= step < total_steps:
        raise ValueError("invalid planned optimizer step")
    warmup = max(1, math.ceil(total_steps * 0.05))
    if step < warmup:
        return (step + 1) / warmup
    progress = (step - warmup + 1) / max(1, total_steps - warmup)
    return 0.1 + 0.9 * (1 + math.cos(math.pi * progress)) / 2


def improved(loss, best):
    if not math.isfinite(loss) or loss < 0:
        raise ValueError("selection loss must be finite and nonnegative")
    return loss < best - 1e-6


def select_grid(results):
    expected = {Trial(width, rate).sha256() for width in (64, 128) for rate in (0.0003, 0.001)}
    if len(results) != 4 or {r["trial_sha256"] for r in results} != expected:
        raise ValueError("all four unique fixed-grid trials must complete")
    for result in results:
        if result["status"] != "verified" or not math.isfinite(result["selection_log_loss"]):
            raise ValueError("incomplete or nonfinite search result")
        if result["selection_log_loss"] < 0 or result["parameter_count"] <= 0:
            raise ValueError("invalid trial metrics")
    return min(results, key=lambda r: (r["selection_log_loss"], r["parameter_count"], r["trial_sha256"]))
