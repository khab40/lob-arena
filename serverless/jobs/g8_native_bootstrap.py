"""Import reviewed overlays directly from read-only injected ZIPs, without extraction."""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.util
import io
import os
from pathlib import Path
import runpy
import sys
import zipfile

# Independent bootstrap cannot import unverified overlays for these constants.
MAX_INJECTION = 40 * 1024
ARCHIVE_COUNT = 3


class Overlays(importlib.abc.MetaPathFinder, importlib.abc.SourceLoader):
    def __init__(self, sources):
        self.sources = sources

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.sources:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def get_filename(self, fullname):
        return self.sources[fullname][0]

    def get_data(self, path):
        for filename, content in self.sources.values():
            if filename == path:
                return content
        raise OSError("unreviewed overlay path")


def install(package):
    sources = {}
    for index in range(ARCHIVE_COUNT):
        path = package / f"native-code-{index}.zip"
        if (path.absolute() != path.resolve() or not path.is_file() or path.stat().st_size > MAX_INJECTION
                or not os.statvfs(path).f_flag & os.ST_RDONLY):
            raise ValueError("bounded read-only code archive required")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != os.environ.get(f"G8_NATIVE_CODE_{index}_SHA256"):
            raise ValueError("code archive differs from injected trust anchor")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if not 1 <= len(archive.infolist()) <= 32:
                raise ValueError("bounded code inventory required")
            for info in archive.infolist():
                name = info.filename.removesuffix(".py")
                if (not info.filename.endswith(".py") or not all(p.isidentifier() for p in name.split("."))
                        or name in sources or not 0 < info.file_size <= 65536 or info.flag_bits & 1
                        or info.compress_type != zipfile.ZIP_DEFLATED):
                    raise ValueError("invalid or duplicate code member")
                sources[name] = (str(path) + "/" + info.filename, archive.read(info))
    conflicts = set(sources) & set(sys.modules)
    if conflicts:
        raise ValueError("reviewed overlay already imported")
    finder = Overlays(sources)
    sys.meta_path.insert(0, finder)
    return finder


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    install(Path(__file__).resolve().parent)
    runpy.run_module("run_g8_native_rehearsal", run_name="__main__")
