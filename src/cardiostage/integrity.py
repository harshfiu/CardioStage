"""
Integrity checks for model bundles (security finding SEC-05).

Model bundles are saved with joblib, which uses Python's pickle format.
Loading a pickle can run arbitrary code, so a tampered, corrupted or swapped
file is dangerous, not just wrong.

Defence: when bundles are built, record each file's SHA-256 fingerprint in
models/manifest.json. Before loading, recompute the fingerprint and refuse to
load if it doesn't match (or if the file isn't in the manifest at all).

What this protects against:
  - a bundle copied in from somewhere else (it won't be in your manifest),
  - accidental corruption or partial copies,
  - a file swapped after building, if the manifest is left alone.
What it does NOT protect against:
  - someone who can rewrite BOTH the bundle and the manifest (anyone with
    write access to models/). Keep models/ writable only by you, and never
    load bundles from untrusted sources.

Usage:
    python -m cardiostage.integrity            # (re)write the manifest for current bundles
"""

import hashlib
import json
from pathlib import Path

from cardiostage import config

MANIFEST_PATH = config.MODELS_DIR / "manifest.json"


class IntegrityError(RuntimeError):
    """A model file failed its integrity check and must not be loaded."""


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 hex digest of a file, read in 1 MB chunks (bundles are up to ~85 MB)."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(paths, manifest_path: Path = MANIFEST_PATH) -> dict:
    """Record the fingerprint of each given file (keyed by file name)."""
    manifest = {Path(p).name: sha256_of(Path(p)) for p in paths}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify(path: Path, manifest_path: Path = MANIFEST_PATH) -> None:
    """Raise IntegrityError unless `path` matches its recorded fingerprint."""
    path = Path(path)
    if not manifest_path.exists():
        raise IntegrityError(
            f"No integrity manifest at {manifest_path.name}. Rebuild the models with "
            "`python -m cardiostage.train_all` (or, for bundles you built yourself, "
            "`python -m cardiostage.integrity`)."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get(path.name)
    if expected is None:
        raise IntegrityError(f"{path.name} is not listed in the integrity manifest.")
    if sha256_of(path) != expected:
        raise IntegrityError(
            f"{path.name} does not match its recorded fingerprint. It may have been "
            "modified, corrupted or replaced. Refusing to load it."
        )


def load(path: Path, manifest_path: Path = MANIFEST_PATH):
    """Verify a pickle against the manifest, then load it. Use instead of joblib.load."""
    import joblib

    verify(path, manifest_path)
    return joblib.load(path)


def stage_bundle_paths() -> list:
    """Every pickle the code loads back: stage bundles + saved out-of-fold predictions."""
    paths = [config.MODELS_DIR / f"stage{s}.joblib" for s in config.STAGES]
    for extra in ("phase4_oof.joblib", "phase5_oof.joblib"):
        if (config.MODELS_DIR / extra).exists():
            paths.append(config.MODELS_DIR / extra)
    return paths


if __name__ == "__main__":
    written = write_manifest(stage_bundle_paths())
    for name, digest in written.items():
        print(f"{name}: {digest[:16]}…")
    print(f"Manifest written to {MANIFEST_PATH}")
