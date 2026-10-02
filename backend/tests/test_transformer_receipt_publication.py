"""Inert filesystem fault injection; no payload, model or numerical imports."""
from pathlib import Path

import pytest

from app.ml.transformer import receipt_publication as publication


PAYLOAD = b'{"source_separation_verified":true}'


def inject_stream(monkeypatch, output, fault=None):
    factory = publication.NamedTemporaryFile
    created, closed = [], []

    class Stream:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            result = self.stream.__exit__(*args)
            closed.append(True)
            if fault == "close":
                raise OSError("injected close failure")
            return result

        def write(self, raw):
            assert not output.exists()
            if fault == "write":
                self.stream.write(raw[:3])
                raise OSError("injected partial write failure")
            if fault == "short":
                return self.stream.write(raw[:-1])
            return self.stream.write(raw)

        def flush(self):
            if fault == "flush":
                raise OSError("injected flush failure")
            return self.stream.flush()

    def temporary(**kwargs):
        assert kwargs == {"mode": "wb", "prefix": "." + output.name + ".",
                          "suffix": ".tmp", "dir": output.parent, "delete": False}
        stream = factory(**kwargs)
        created.append(Path(stream.name))
        return Stream(stream)

    monkeypatch.setattr(publication, "NamedTemporaryFile", temporary)
    return created, closed


def test_complete_receipt_becomes_visible_only_after_successful_close(tmp_path, monkeypatch):
    output = tmp_path / "receipt.json"
    created, closed = inject_stream(monkeypatch, output)
    link = publication.os.link

    def publish(source, destination):
        assert closed == [True] and not output.exists()
        assert Path(source).read_bytes() == PAYLOAD
        link(source, destination)
        assert output.read_bytes() == PAYLOAD

    monkeypatch.setattr(publication.os, "link", publish)
    assert publication.publish_receipt(output, PAYLOAD) is None
    assert output.read_bytes() == PAYLOAD
    assert len(created) == 1 and not created[0].exists()
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("fault", ["write", "short", "flush", "fsync", "close", "link"])
def test_failure_before_publication_leaves_no_partial_receipt(tmp_path, monkeypatch, fault):
    output = tmp_path / "receipt.json"
    created, _ = inject_stream(monkeypatch, output, fault)

    def fail(*args):
        raise OSError("injected " + fault + " failure")

    if fault in ("fsync", "link"):
        monkeypatch.setattr(publication.os, fault, fail)
    with pytest.raises((OSError, ValueError)):
        publication.publish_receipt(output, PAYLOAD)
    assert not output.exists()
    assert len(created) == 1 and not created[0].exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["file", "symlink", "directory"])
def test_concurrent_destination_is_never_replaced(tmp_path, monkeypatch, kind):
    output = tmp_path / "receipt.json"
    created, _ = inject_stream(monkeypatch, output)
    link = publication.os.link

    def race(source, destination):
        if kind == "file":
            output.write_bytes(b"existing evidence")
        elif kind == "symlink":
            output.symlink_to("missing-evidence.json")
        else:
            output.mkdir()
        link(source, destination)

    monkeypatch.setattr(publication.os, "link", race)
    with pytest.raises(FileExistsError):
        publication.publish_receipt(output, PAYLOAD)
    assert len(created) == 1 and not created[0].exists()
    if kind == "file":
        assert output.read_bytes() == b"existing evidence"
    elif kind == "symlink":
        assert output.is_symlink() and output.readlink() == Path("missing-evidence.json")
    else:
        assert output.is_dir() and list(output.iterdir()) == []


def test_preexisting_receipt_is_unchanged(tmp_path):
    output = tmp_path / "receipt.json"
    output.write_bytes(b"retained evidence")
    with pytest.raises(FileExistsError):
        publication.publish_receipt(output, PAYLOAD)
    assert output.read_bytes() == b"retained evidence"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("published", [False, True])
def test_cleanup_failure_never_removes_final_receipt(tmp_path, monkeypatch, published):
    output = tmp_path / "receipt.json"
    created, _ = inject_stream(monkeypatch, output)

    def cleanup(path, *args, **kwargs):
        assert path == created[0] and path != output
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(Path, "unlink", cleanup)
    if published:
        assert publication.publish_receipt(output, PAYLOAD) == created[0]
        assert output.read_bytes() == PAYLOAD
    else:
        def fail_link(*args):
            raise OSError("injected link failure")

        monkeypatch.setattr(publication.os, "link", fail_link)
        with pytest.raises(OSError, match="cleanup failure"):
            publication.publish_receipt(output, PAYLOAD)
        assert not output.exists()
    assert created[0].read_bytes() == PAYLOAD
