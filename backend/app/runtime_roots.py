"""Reject writable/public roots overlapping retained private custody before startup."""

from pathlib import Path


def validate_runtime_roots(settings, screenshots: Path) -> None:
    public = (settings.arena_output_dir.resolve(), screenshots.resolve())
    private = []
    for directory in (settings.research_saved_scores_dir,
                      settings.ceo_demo_state_dir if settings.ceo_demo_enabled else None):
        if directory is None:
            continue
        path = Path(directory)
        if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Unsafe private runtime root")
        resolved = path.resolve()
        for other in (*public, *private):
            if resolved.is_relative_to(other) or other.is_relative_to(resolved):
                raise ValueError("Private evidence overlaps another runtime root")
        private.append(resolved)
    # Preserve the ordinary research reader's existing admission; in the demo,
    # missing custody disables only its prepared source, not the working product.
    if not settings.ceo_demo_enabled and (settings.research_saved_scores_enabled
                                         or settings.research_saved_scores_dir is not None):
        from app.research.saved_score_io import validate_private_roots
        validate_private_roots(settings.research_saved_scores_dir, public)
