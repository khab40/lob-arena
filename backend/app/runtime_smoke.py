from __future__ import annotations

import importlib.util
import sys


def _absent(name: str) -> bool:
    parent = name.rpartition(".")[0]
    if parent and importlib.util.find_spec(parent) is None:
        return True
    return importlib.util.find_spec(name) is None


def main() -> None:
    import app.main  # noqa: F401

    assert "app.arena.engine" not in sys.modules
    assert _absent("app.websocket.routes")
    assert _absent("app.contracts.python_reference")
    if "--minimal-image" in sys.argv:
        assert _absent("grpc")
        assert _absent("google.protobuf")
        from google.oauth2.id_token import verify_oauth2_token

        assert callable(verify_oauth2_token)


if __name__ == "__main__":
    main()
