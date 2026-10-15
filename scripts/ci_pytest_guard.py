"""Pytest placement hooks: validate before collection, select before fixture setup."""
from pathlib import Path

import pytest

from scripts.ci_workload_policy import item_node, validate_inventory


def pytest_configure(config):
    root = Path(__file__).resolve().parents[1]
    try:
        config._arena_workload_inventory = validate_inventory(root)
        config._arena_workload_root = root
    except (ValueError, OSError) as error:
        raise pytest.UsageError("Workload placement refused before collection: " + str(error)) from error


def select_items(items, inventory, root, *, authorization=None):
    """No model fixture runs in default mode, including explicitly requested nodes."""
    if authorization is not None:
        raise ValueError("model execution requires a separately reviewed Nebius runner")
    selected, excluded = [], []
    for item in items:
        node = item_node(item, root)
        kind = inventory["classification"].get(node)
        if kind is None:
            raise ValueError("unknown collected test; classification review required: " + node)
        wanted = "inert"
        (selected if kind == wanted else excluded).append(item)
    return selected, excluded


def pytest_collection_modifyitems(config, items):
    inventory = config._arena_workload_inventory
    try:
        chosen, excluded = select_items(items, inventory, config._arena_workload_root)
    except (ValueError, OSError) as error:
        raise pytest.UsageError("Workload placement refused before fixture setup: " + str(error)) from error
    if excluded:
        config.hook.pytest_deselected(items=excluded)
    items[:] = chosen


def pytest_report_header(config):
    inventory = config._arena_workload_inventory
    return ("Reviewed workload placement: default inert checks; "
            f"{len(inventory['model_nodes'])} model definitions require separately approved Nebius verification. "
            "Inert CI does not verify those numerical assertions.")
