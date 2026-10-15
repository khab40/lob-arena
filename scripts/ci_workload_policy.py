"""Static reviewed test placement; never import application or test modules."""
import ast
import hashlib
import json
from pathlib import Path

SCHEMA = "reviewed_ci_workload_inventory_v1"
INDEX = "configs/ci/workloads/index.json"
PIN = "configs/ci/workloads-pin.json"
MAX_FILE = 4 * 1024**2


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_paths(root):
    root = Path(root)
    paths = set()
    for folder in ("backend/app", "backend/tests", "serverless", "scripts"):
        base = root / folder
        if base.is_symlink():
            raise ValueError("workload source directory is a symlink")
        for path in base.rglob("*.py"):
            if any(part in {".venv", "__pycache__", ".git"} for part in path.parts):
                continue
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise ValueError("workload source path is a symlink")
            paths.add(path.relative_to(root).as_posix())
    for name in ("backend/conftest.py", "backend/pyproject.toml", "backend/uv.lock",
                 "configs/benchmark/nasdaq-public-sample-v1.json"):
        if (root / name).exists():
            paths.add(name)
    return sorted(paths)


def read_bytes(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("workload inventory/source path is a symlink")
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE + 1)
    if not raw or len(raw) > MAX_FILE:
        raise ValueError("workload inventory/source bytes exceed bounds")
    return raw


def _stable_ast_dump(node):
    """Match the reviewed 3.14 parsed-AST format on supported older Pythons."""
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            # Parser list fields are structural; empty additions such as
            # type_params must not change a previously reviewed function hash.
            if isinstance(value, list) and not value:
                continue
            if value is None and getattr(type(node), name, ...) is None:
                continue
            fields.append(name + "=" + _stable_ast_dump(value))
        return type(node).__name__ + "(" + ", ".join(fields) + ")"
    if isinstance(node, list):
        return "[" + ", ".join(_stable_ast_dump(value) for value in node) + "]"
    return repr(node)


def test_nodes(raw):
    tree = ast.parse(raw)
    nodes = {}
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
            nodes[item.name] = sha(_stable_ast_dump(item).encode())
        elif isinstance(item, ast.ClassDef) and item.name.startswith("Test"):
            for method in item.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name.startswith("test_"):
                    nodes[item.name + "::" + method.name] = sha(_stable_ast_dump(method).encode())
    return nodes


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate workload inventory field")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite inventory")))


def validate_inventory(root, *, index_path=INDEX):
    """Authenticate complete source and function membership before pytest collection."""
    root = Path(root)
    index_file = root / index_path
    index_raw = read_bytes(index_file)
    pin = _json(read_bytes(root / PIN))
    if (type(pin) is not dict or set(pin) != {"schema_version", "index_sha256"}
            or pin["schema_version"] != "reviewed_ci_workload_pin_v1"
            or sha(index_raw) != pin["index_sha256"]):
        raise ValueError("externally pinned workload classification differs; review required")
    index = _json(index_raw)
    if (type(index) is not dict or set(index) != {"schema_version", "audit_sha256", "chunks", "model_definition_count"}
            or index["schema_version"] != SCHEMA or type(index["chunks"]) is not list
            or not 1 <= len(index["chunks"]) <= 32 or type(index["model_definition_count"]) is not int
            or not 1 <= index["model_definition_count"] <= 1000):
        raise ValueError("reviewed workload inventory schema differs")
    records, classifications, chunks = {}, {}, set()
    for ref in index["chunks"]:
        if type(ref) is not dict or set(ref) != {"path", "sha256"}:
            raise ValueError("workload inventory chunk reference differs")
        name = ref["path"]
        if (not isinstance(name, str) or not name.startswith("source-") or not name.endswith(".json")
                or Path(name).name != name or name in chunks):
            raise ValueError("workload inventory chunk path differs")
        chunks.add(name)
        raw = read_bytes(index_file.parent / name)
        if sha(raw) != ref["sha256"]:
            raise ValueError("workload inventory chunk hash differs")
        rows = _json(raw)
        if type(rows) is not list or not 1 <= len(rows) <= 128:
            raise ValueError("workload inventory chunk membership differs")
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "sha256", "tests"}:
                raise ValueError("workload source record differs")
            name = row["path"]
            if not isinstance(name, str) or name in records or type(row["tests"]) is not list:
                raise ValueError("workload source membership differs")
            records[name] = row
    expected = source_paths(root)
    if set(records) != set(expected):
        raise ValueError("unknown or missing workload source; refresh classification and obtain review")
    for name in expected:
        row, raw = records[name], read_bytes(root / name)
        if sha(raw) != row["sha256"]:
            raise ValueError("changed workload source; refresh classification and obtain review: " + name)
        definitions = test_nodes(raw) if name.startswith("backend/tests/") and Path(name).name.startswith("test_") else {}
        found = set()
        for node in row["tests"]:
            if (type(node) is not dict or set(node) != {"name", "ast_sha256", "classification"}
                    or node["name"] not in definitions or node["name"] in found
                    or node["ast_sha256"] != definitions[node["name"]]
                    or node["classification"] not in {"inert", "nebius_cpu_model_workload"}):
                raise ValueError("workload test classification differs: " + name)
            found.add(node["name"])
            classifications[name + "::" + node["name"]] = node["classification"]
        if found != set(definitions):
            raise ValueError("unknown or missing workload test definition: " + name)
    if sum(value == "nebius_cpu_model_workload" for value in classifications.values()) != index["model_definition_count"]:
        raise ValueError("workload model-definition count differs")
    return {"inventory_sha256": sha(index_raw), "classification": classifications,
            "model_nodes": tuple(key for key, value in classifications.items() if value == "nebius_cpu_model_workload")}


def item_node(item, root):
    # Parameter suffixes inherit the reviewed function classification.
    suffix = "::".join(item.nodeid.split("::")[1:]).split("[", 1)[0]
    return Path(item.path).resolve().relative_to(Path(root).resolve()).as_posix() + "::" + suffix
