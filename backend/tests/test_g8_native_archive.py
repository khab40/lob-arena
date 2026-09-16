"""Static packaging/import-hook checks; no frozen runtime or model execution."""
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from serverless.jobs import g8_native_archive as archive, g8_native_bootstrap as bootstrap
from serverless.jobs import g8_native_contract as contract


def test_actual_reviewed_sources_fit_two_deterministic_archives(tmp_path):
    root = Path(__file__).resolve().parents[2]
    code = {name: (root / ("backend/app/ml/lightgbm" if name.removesuffix(".py") in contract.MODULES
                          else "serverless/jobs") / name).read_bytes() for name in contract.CODE_PATHS}
    packed = archive.build(code)
    assert packed == archive.build(dict(reversed(list(code.items()))))
    assert set(packed) == set(contract.ARCHIVES)
    for name, raw in packed.items():
        assert len(raw) <= 65536
        (tmp_path / name).write_bytes(raw)
    for name, raw in code.items():
        assert archive.read_code(tmp_path, name) == raw
    assert not list(tmp_path.glob("*.py"))


def test_uncompressible_sources_fail_before_submission():
    import random
    random_source = random.Random(123)
    code = {name: random_source.randbytes(60000) for name in contract.CODE_PATHS}
    with pytest.raises(ValueError, match="injected-file limit"):
        archive.build(code)


@pytest.mark.parametrize("change", ["duplicate", "extra", "oversize", "stored"])
def test_archive_member_inventory_is_fail_closed(tmp_path, change):
    code = {name: b"# inert source\n" for name in contract.CODE_PATHS}
    for name, raw in archive.build(code).items():
        (tmp_path / name).write_bytes(raw)
    first = contract.ARCHIVES[0]
    names = archive.groups()[first]
    entries = [(archive.member(n), code[n]) for n in names]
    if change == "duplicate":
        entries[-1] = entries[0]
    elif change == "extra":
        entries.append(("../escape.py", b"bad"))
    elif change == "oversize":
        entries[0] = (entries[0][0], b"x" * 65537)
    with zipfile.ZipFile(tmp_path / first, "w", compression=(zipfile.ZIP_STORED if change == "stored"
                                                           else zipfile.ZIP_DEFLATED)) as target:
        for name, raw in entries:
            target.writestr(name, raw)
    with pytest.raises(ValueError, match="inventory"):
        archive.read_code(tmp_path, names[0])


def inert_archives(tmp_path, monkeypatch, *, duplicate=False):
    monkeypatch.setattr(bootstrap.os, "statvfs", lambda _: SimpleNamespace(f_flag=bootstrap.os.ST_RDONLY))
    for index, filename in enumerate(contract.ARCHIVES):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as target:
            name = "g8_static_probe" if index == 0 or duplicate else "g8_static_second"
            target.writestr(name + ".py", b"VALUE = 42\n")
        raw = data.getvalue()
        (tmp_path / filename).write_bytes(raw)
        monkeypatch.setenv(f"G8_NATIVE_CODE_{index}_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(bootstrap.sys, "meta_path", list(bootstrap.sys.meta_path))


def test_loader_uses_archive_source_without_extraction(tmp_path, monkeypatch):
    inert_archives(tmp_path, monkeypatch)
    finder = bootstrap.install(tmp_path)
    spec = finder.find_spec("g8_static_probe")
    module = bootstrap.importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # Only the inert VALUE assignment above.
    assert module.VALUE == 42
    assert module.__file__.endswith("native-code-0.zip/g8_static_probe.py")
    assert finder.find_spec("unreviewed") is None
    assert sorted(p.name for p in tmp_path.iterdir()) == list(contract.ARCHIVES)


@pytest.mark.parametrize("change", ["hash", "writable", "duplicate", "preloaded"])
def test_loader_refuses_untrusted_or_ambiguous_code(tmp_path, monkeypatch, change):
    inert_archives(tmp_path, monkeypatch, duplicate=change == "duplicate")
    if change == "hash":
        monkeypatch.setenv("G8_NATIVE_CODE_0_SHA256", "a" * 64)
    elif change == "writable":
        monkeypatch.setattr(bootstrap.os, "statvfs", lambda _: SimpleNamespace(f_flag=0))
    elif change == "preloaded":
        monkeypatch.setitem(bootstrap.sys.modules, "g8_static_probe", object())
    before = list(bootstrap.sys.meta_path)
    with pytest.raises(ValueError):
        bootstrap.install(tmp_path)
    assert bootstrap.sys.meta_path == before
