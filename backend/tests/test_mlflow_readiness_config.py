import stat

import pytest

from deployments.mlflow import readiness_config as config

ORIGINAL = (b"# keep exact comments\r\nPASSWORD=opaque$'value'\r\n"
            b"MLFLOW_EXPORTER_EXPERIMENTS=existing,custom/namespace\r\n"
            b"MLFLOW_EXPORTER_MODEL_NAMES=existing-model")


def test_additive_bytes_and_atomic_private_idempotency(tmp_path):
    path = tmp_path / "mlflow.env"
    path.write_bytes(ORIGINAL)
    path.chmod(0o600)
    old_inode = path.stat().st_ino
    assert config.update_allowlists(path)["changed"]
    expected = ORIGINAL.replace(b"custom/namespace", b"custom/namespace,lob-arena/transformer-development")
    expected += b",lob-arena-transformer-attack-active"
    assert path.read_bytes() == expected
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_ino != old_inode
    assert not config.update_allowlists(path)["changed"]
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("replacement", [b"", b'"old"', b"old # comment", b"old,$VAR", b"old, two"])
def test_ambiguous_values_are_rejected(replacement):
    with pytest.raises(ValueError):
        config.append_allowlists(ORIGINAL.replace(b"existing-model", replacement))


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "export", "space"])
def test_unsupported_or_duplicate_keys_are_rejected(mutation):
    key = b"MLFLOW_EXPORTER_MODEL_NAMES"
    content = {"duplicate": ORIGINAL + b"\n" + key + b"=another",
               "missing": ORIGINAL[:ORIGINAL.index(key)],
               "export": ORIGINAL.replace(key, b"export " + key),
               "space": ORIGINAL.replace(key, b" " + key)}[mutation]
    with pytest.raises(ValueError):
        config.append_allowlists(content)


def test_symlink_public_file_and_intervening_change_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "mlflow.env"
    path.write_bytes(ORIGINAL)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        config.update_allowlists(path)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        config.update_allowlists(link)
    original = config.append_allowlists
    def concurrent(content):
        path.write_bytes(b"operator update")
        return original(content)
    monkeypatch.setattr(config, "append_allowlists", concurrent)
    with pytest.raises(ValueError, match="changed during"):
        config.update_allowlists(path)
    assert path.read_bytes() == b"operator update"
    assert not list(tmp_path.glob(".allowlists-*"))


def test_failed_fsync_preserves_original_file(tmp_path, monkeypatch):
    path = tmp_path / "mlflow.env"
    path.write_bytes(ORIGINAL)
    path.chmod(0o600)
    def fail(_):
        raise OSError("disk failure")
    monkeypatch.setattr(config.os, "fsync", fail)
    with pytest.raises(OSError):
        config.update_allowlists(path)
    assert path.read_bytes() == ORIGINAL and list(tmp_path.iterdir()) == [path]
