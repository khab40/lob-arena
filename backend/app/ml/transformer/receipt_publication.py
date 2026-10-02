"""Publish complete local receipts atomically without replacing existing evidence."""
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def publish_receipt(output: Path, payload: bytes) -> Path | None:
    """Return an owned temporary alias only if cleanup failed after publication.

    The hard link is the authoritative exclusive claim, including concurrent
    creators and dangling symlinks. No final path is removed on any failure.
    Atomic visibility does not promise directory-entry persistence after power loss.
    """
    temporary = None
    published = False
    cleanup_pending = None
    try:
        with NamedTemporaryFile(mode="wb", prefix=f".{output.name}.", suffix=".tmp",
                dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            if stream.write(payload) != len(payload):
                raise OSError("short receipt write")
            stream.flush()
            os.fsync(stream.fileno())
        # Closing can surface delayed write errors; publish only after it succeeds.
        os.link(temporary, output)
        published = True
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                if not published:
                    raise
                # Complete evidence is already visible: report the alias, never roll back.
                cleanup_pending = temporary
    return cleanup_pending
