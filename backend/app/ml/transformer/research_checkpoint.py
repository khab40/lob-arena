"""Immutable epoch checkpoints; upload acknowledgement precedes epoch progress."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import random

import numpy as np
import torch


def file_sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def rng_state():
    state = np.random.get_state()
    return {"python": random.getstate(), "numpy": [state[0], state[1].tolist(), *state[2:]],
            "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}


def restore_rng(state):
    random.setstate(state["python"])
    np.random.set_state((state["numpy"][0], np.array(state["numpy"][1], dtype=np.uint32), *state["numpy"][2:]))
    torch.set_rng_state(state["torch"])
    torch.cuda.set_rng_state_all(state["cuda"])


def write_checkpoint(output, *, model, optimizer, trial, bindings, progress, publish):
    path = output / f'epoch-{progress["epoch"]:02}.pt'
    state = {"schema": "transformer_research_epoch_v1", "trial": asdict(trial), "bindings": bindings,
             "model": model.state_dict(), "optimizer": optimizer.state_dict(), "rng": rng_state(),
             "progress": progress, "sampler_position": 0, "precision": "float32"}
    # Partial files cannot be mistaken for an acknowledged checkpoint: only a
    # returned publication receipt can enter the durable epoch journal.
    with path.open("xb") as stream:
        torch.save(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    checksum = file_sha(path)
    receipt = publish(path, checksum)
    if (not isinstance(receipt, dict) or receipt.get("sha256") != checksum
            or not isinstance(receipt.get("version_id"), str) or not receipt["version_id"]
            or receipt["version_id"] == "null"):
        raise ValueError("versioned checkpoint publication not acknowledged")
    record = {"epoch": progress["epoch"], "name": path.name, **receipt}
    with (output / f'epoch-{progress["epoch"]:02}.json').open("x") as stream:
        json.dump(record, stream, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    return record


def load_checkpoint(path, expected_sha, *, model, optimizer, trial, bindings):
    if file_sha(path) != expected_sha:
        raise ValueError("checkpoint bytes differ from verified version")
    state = torch.load(path, map_location="cpu", weights_only=True)
    if (state["schema"] != "transformer_research_epoch_v1" or state["trial"] != asdict(trial)
            or state["bindings"] != bindings or state["sampler_position"] != 0
            or state["precision"] != "float32"):
        raise ValueError("checkpoint code/data/config binding changed")
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])
    restore_rng(state["rng"])
    return state["progress"]
