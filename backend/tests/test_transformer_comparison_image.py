"""Source transformation only; never import the model or build a container."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("comparison_image", ROOT / "scripts/transformer_comparison_image.py")
image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image)


def source():
    return (ROOT / "backend/app/ml/transformer/research_run.py").read_text()


def test_overlay_preserves_numerical_source_and_keeps_only_compatibility(tmp_path):
    image.prepare(ROOT, tmp_path / "context")
    patched = (tmp_path / "context/research_run.py").read_text()
    assert "origin = checkpoint_origin" in patched
    assert "grid_selected" not in patched and "progress_event=" not in patched
    assert len(list((tmp_path / "context").iterdir())) == 9
    with pytest.raises(FileExistsError):
        image.prepare(ROOT, tmp_path / "context")


@pytest.mark.parametrize("old,new", [("configure(42)", "configure(7)"),
    ("weights_only=True", "weights_only=False"), ("weight_decay=.01", "weight_decay=.02"),
    ("progress_event=store.event", "progress_event=None")])
def test_unreviewed_numerical_or_patch_changes_fail(old, new):
    with pytest.raises(ValueError):
        image.frozen_run(source().replace(old, new))
