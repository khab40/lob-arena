"""Build an inert overlay context without rebuilding numerical dependencies."""
import argparse
import hashlib
from pathlib import Path
import shutil

BASE_RUN_SHA = "84398f00a3696c4c73ea29029f46a72e421e06f203f4d8d712a7e6dfb26e8810"
OVERLAY = ("research_confirmation_contract.py", "research_comparison_contract.py",
    "research_publication_contract.py", "research_execution_spec.py", "research_storage.py",
    "research_readback.py", "research_comparison_readback.py")


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("frozen runtime patch boundary differs")
    return text.replace(old, new)


def frozen_run(current):
    # The current repository has newer progress logging. Keep the trained image's
    # logger and training call unchanged; only admit checkpoint-origin metadata.
    for old, new in (
        ("from .research_progress import grid_selected\n", ""),
        ("        grid_selected(grid, winner, persist=store.event)\n", ""),
        ("expires=expires, progress_event=store.event)", "expires=expires)"),
    ):
        current = replace_once(current, old, new)
    patches = (
        ("from .research_comparison_contract import checkpoint_origin, is_comparison\n", ""),
        ('    origin = None\n    if is_comparison(store.request):\n'
         '        if not stability["passed"]:\n'
         '            raise ValueError("comparison requires passed seed stability")\n'
         '        origin = checkpoint_origin(store.request, prior, bindings)\n', ""),
        ('model = selected_model(checkpoint, item["sha256"], trial, origin["bindings"] if origin else bindings)',
         'model = selected_model(checkpoint, item["sha256"], trial, bindings)'),
        ('        **({"checkpoint_origin": origin, "execution_bindings": bindings} if origin else {}),\n', ""),
    )
    original = current
    for new, old in patches:
        original = replace_once(original, new, old)
    if hashlib.sha256(original.encode()).hexdigest() != BASE_RUN_SHA:
        raise ValueError("numerical runtime differs outside the reviewed compatibility patch")
    return current


def prepare(repository, output):
    module = repository / "backend/app/ml/transformer"
    patched = frozen_run((module / "research_run.py").read_text())
    output.mkdir(parents=True, exist_ok=False)
    for name in OVERLAY:
        shutil.copyfile(module / name, output / name)
    (output / "research_run.py").write_text(patched)
    shutil.copyfile(repository / "serverless/transformer_research/Dockerfile.comparison", output / "Dockerfile")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.repository, args.output)
