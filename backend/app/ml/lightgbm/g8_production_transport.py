"""Native production code transport; only stdlib and no model execution."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import sys
import zipfile

ARCHIVES = tuple(f"native-code-{index}.zip" for index in range(3))
BOOTSTRAP = "g8_native_bootstrap.py"
PACKAGE = "/g8-package/production"
DEPLOYMENT_IMAGE = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/g:dc32b12d7216bfee"
MAX_FILE = 40960


def module_name(path):
    if path.startswith("/job/backend/"):
        return path.removeprefix("/job/backend/").removesuffix(".py").replace("/", ".")
    if path.startswith("/job/g8/"):
        return path.removeprefix("/job/g8/").removesuffix(".py")
    raise ValueError("unreviewed module path")


def build_archives(code, paths):
    """Same bounded deterministic ZIP format consumed by the proven bootstrap."""
    if set(code) != set(paths):
        raise ValueError("exact production code inventory required")
    archives = {}
    for index, archive in enumerate(ARCHIVES):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
            for name in sorted(code)[index::3]:
                if not 0 < len(code[name]) <= 65536:
                    raise ValueError("bounded production code member required")
                member = module_name(paths[name]) + ".py"
                info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100444 << 16
                target.writestr(info, code[name], compresslevel=9)
        archives[archive] = buffer.getvalue()
        if len(archives[archive]) > MAX_FILE:
            raise ValueError("production archive exceeds bootstrap parser bound")
    return archives


def verify_archives(root, paths):
    expected = build_archives({name: (root / name).read_bytes() for name in paths}, paths)
    for name, raw in expected.items():
        if (root / name).read_bytes() != raw:
            raise ValueError("production archive differs from signed source: " + name)


def verify_runtime(root, plan, paths):
    """Verify actual in-memory imports and read-only files before final access."""
    if str(root) != PACKAGE or os.environ.get("G8_NATIVE_TARGET") != "production":
        raise ValueError("production package must use the reviewed native bootstrap")
    for path in root.iterdir():
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError("production package must be read-only")
    injected = Path("/job/g8") / BOOTSTRAP
    if (not os.statvfs(injected).f_flag & os.ST_RDONLY
            or hashlib.sha256(injected.read_bytes()).hexdigest() != plan.files[BOOTSTRAP].sha256):
        raise ValueError("injected production bootstrap differs")
    for index, archive in enumerate(ARCHIVES):
        if os.environ.get(f"G8_NATIVE_CODE_{index}_SHA256") != plan.files[archive].sha256:
            raise ValueError("production archive trust anchor differs")
    loaders = [finder for finder in sys.meta_path if hasattr(finder, "sources")]
    expected_names = {module_name(path) for path in paths.values()}
    if len(loaders) != 1 or set(loaders[0].sources) != expected_names:
        raise ValueError("exact in-memory production overlay required")
    loader = loaders[0]
    for name, path in paths.items():
        module = module_name(path)
        if hashlib.sha256(loader.get_data(loader.get_filename(module))).hexdigest() != plan.files[name].sha256:
            raise ValueError("runtime production overlay differs: " + name)
        if module in sys.modules and sys.modules[module].__loader__ is not loader:
            raise ValueError("production overlay imported outside verified bootstrap")
