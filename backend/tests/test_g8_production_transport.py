"""Static transport checks use inert code, never the frozen model runtime."""
import hashlib
import ast
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.ml.lightgbm import g8_production_transport as transport
from serverless.jobs import g8_native_bootstrap as bootstrap


def test_actual_source_archives_fit_bootstrap_without_importing_runtime():
    repo = Path(__file__).resolve().parents[2]
    contract = repo / "backend/app/ml/lightgbm/g8_replacement.py"
    modules = next(ast.literal_eval(node.value) for node in ast.parse(contract.read_text()).body
                   if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "MODULES")
    paths = {name + ".py": "/job/backend/app/ml/lightgbm/" + name + ".py" for name in modules}
    paths.update({name: "/job/g8/" + name for name in ("run_lightgbm_g8.py", "run_lightgbm_g8_replacement.py")})
    code = {name: (repo / ("backend/app/ml/lightgbm" if name.removesuffix(".py") in modules
                           else "serverless/jobs") / name).read_bytes() for name in paths}
    assert set(transport.build_archives(code, paths)) == set(transport.ARCHIVES)


@pytest.fixture
def package(tmp_path):
    paths = {f"inert_{n}.py": f"/job/g8/inert_{n}.py" for n in range(3)}
    code = {name: b"VALUE = 3\n" for name in paths}
    files = {**code, **transport.build_archives(code, paths), transport.BOOTSTRAP: b"# inert bootstrap\n"}
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)
    plan = SimpleNamespace(files={name: SimpleNamespace(sha256=hashlib.sha256(raw).hexdigest())
                                  for name, raw in files.items()})
    return tmp_path, paths, plan


def test_deterministic_archives_bind_every_source(package):
    root, paths, _ = package
    transport.verify_archives(root, paths)
    (root / "inert_0.py").write_bytes(b"VALUE = 4\n")
    with pytest.raises(ValueError, match="differs from signed source"):
        transport.verify_archives(root, paths)


def test_archive_corruption_rejected_without_import(package):
    root, paths, _ = package
    with (root / transport.ARCHIVES[0]).open("ab") as stream:
        stream.write(b"extra")
    with pytest.raises(ValueError, match="differs from signed source"):
        transport.verify_archives(root, paths)


def test_archive_requires_exact_bounded_inventory():
    with pytest.raises(ValueError, match="exact"):
        transport.build_archives({}, {"module.py": "/job/g8/module.py"})
    with pytest.raises(ValueError, match="bounded"):
        transport.build_archives({"module.py": b"x" * 65537}, {"module.py": "/job/g8/module.py"})


@pytest.mark.parametrize("change", [None, "writable", "anchor", "code", "import", "bootstrap", "target"])
def test_actual_loader_and_mount_gate(package, monkeypatch, change):
    root, paths, plan = package
    monkeypatch.setattr(transport, "PACKAGE", str(root))
    monkeypatch.setattr(transport, "Path", lambda value: root)
    monkeypatch.setattr(os, "statvfs", lambda p: SimpleNamespace(f_flag=os.ST_RDONLY))
    monkeypatch.setenv("G8_NATIVE_TARGET", "production")
    for index, archive in enumerate(transport.ARCHIVES):
        monkeypatch.setenv(f"G8_NATIVE_CODE_{index}_SHA256", plan.files[archive].sha256)
    previous = sys.meta_path[:]
    try:
        loader = bootstrap.install(root)
        if change == "writable":
            monkeypatch.setattr(os, "statvfs", lambda p: SimpleNamespace(f_flag=0))
        elif change == "anchor":
            monkeypatch.setenv("G8_NATIVE_CODE_0_SHA256", "0" * 64)
        elif change == "code":
            loader.sources["inert_0"] = ("changed.py", b"VALUE = 99\n")
        elif change == "import":
            monkeypatch.setitem(sys.modules, "inert_0", SimpleNamespace(__loader__=None))
        elif change == "bootstrap":
            (root / transport.BOOTSTRAP).write_bytes(b"changed")
        elif change == "target":
            monkeypatch.setenv("G8_NATIVE_TARGET", "rehearsal")
        if change:
            with pytest.raises(ValueError):
                transport.verify_runtime(root, plan, paths)
        else:
            transport.verify_runtime(root, plan, paths)
    finally:
        sys.meta_path[:] = previous
