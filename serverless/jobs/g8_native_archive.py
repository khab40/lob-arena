"""Deterministic, bounded code transport; never extract or execute archive members."""
from __future__ import annotations

import io
import zipfile

if __package__:
    from .g8_native_contract import ARCHIVES, CODE_PATHS, MODULES
else:
    from g8_native_contract import ARCHIVES, CODE_PATHS, MODULES


def member(name):
    stem = name.removesuffix(".py")
    return ("app.ml.lightgbm." if stem in MODULES else "") + name


def groups():
    names = sorted(CODE_PATHS)
    return {archive: names[index::2] for index, archive in enumerate(ARCHIVES)}


def build(code):
    if set(code) != set(CODE_PATHS):
        raise ValueError("exact reviewed code inventory required")
    result = {}
    for archive, names in groups().items():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
            for name in names:
                if not 0 < len(code[name]) <= 65536:
                    raise ValueError("bounded code member required")
                info = zipfile.ZipInfo(member(name), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100444 << 16
                target.writestr(info, code[name], compresslevel=9)
        result[archive] = buffer.getvalue()
        if len(result[archive]) > 65536:
            raise ValueError("code archive exceeds Nebius injected-file limit")
    return result


def read_code(package, name):
    if name not in CODE_PATHS:
        raise ValueError("unreviewed code member")
    for archive, names in groups().items():
        if name not in names:
            continue
        path = package / archive
        if path.absolute() != path.resolve() or path.stat().st_size > 65536:
            raise ValueError("bounded canonical archive required")
        with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as source:
            expected = [member(n) for n in names]
            if source.namelist() != expected or any(
                    not 0 < info.file_size <= 65536 or info.flag_bits & 1
                    or info.compress_type != zipfile.ZIP_DEFLATED for info in source.infolist()):
                raise ValueError("archive members differ from reviewed inventory")
            return source.read(member(name))
    raise ValueError("missing code archive")
