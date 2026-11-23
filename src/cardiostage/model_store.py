"""
Model files for the public app, in the safe skops format.

Why: the trained bundles (models/stage*.joblib) are pickles, and loading a
pickle can run arbitrary code (security finding SEC-05). For the public app
the bundles are converted to skops, which refuses to load anything except
types we have explicitly reviewed and listed in TRUSTED_TYPES below.

Layout: skops becomes extremely slow when one file holds many large model
copies (converting a whole stage-2 bundle ran for 40+ minutes; one range
copy alone takes ~6 s). So each stage is stored as
    stage{N}.skops             everything except the 20 plausible-range copies
    stage{N}-range-{KK}.skops  one file per range copy (KK = 00..19)
and loading puts them back together. All files are packed into ONE archive
(cardiostage-models.zip) so a release needs a single upload.

Where they live: the archive is attached to a GitHub release (generated,
large files don't belong in Git history). deploy/models.json, which IS
committed, records the archive's URL, size and SHA-256 fingerprint AND the
fingerprint of every file inside it. Nothing is extracted unless the archive
matches, and nothing is loaded unless every file matches.

Commands:
    python -m cardiostage.model_store export URL  # joblib bundles -> models/skops/ + archive + manifest
    python -m cardiostage.model_store download    # fetch + verify + extract the released archive
    python -m cardiostage.model_store verify      # check local files against the manifest

Which format the app uses: see predictor.load_bundles.
"""

import copy
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from cardiostage import config, integrity

SKOPS_DIR = config.MODELS_DIR / "skops"
ARCHIVE_NAME = "cardiostage-models.zip"
MANIFEST_PATH = config.PROJECT_ROOT / "deploy" / "models.json"
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024  # refuse anything absurdly large (archive is ~270 MB)

# Every non-standard type inside the bundles, reviewed by hand. skops loads
# plain data, numpy arrays and its built-in scikit-learn/XGBoost support on
# its own; anything else must be listed here or loading fails. Nothing here
# can run code on load beyond constructing these known objects.
TRUSTED_TYPES = [
    "cardiostage.uncertainty.NoveltyDetector",  # our unusual-patient detector
    "cardiostage.uncertainty.SubsampleEnsemble",  # our plausible-range ensemble
    "numpy.dtype",  # numpy data-type descriptors
    "sklearn.tree._tree.Tree",  # the tree structure inside random forests
    "sklearn.calibration._CalibratedClassifier",  # one fold's calibrated model (data holder)
    "sklearn.calibration._SigmoidCalibration",  # fitted sigmoid: two numbers
    "sklearn.model_selection._split.StratifiedKFold",  # cross-validation settings only
    "sklearn.utils._bunch.Bunch",  # a dict with attribute access
    "xgboost.core.Booster",  # XGBoost trees, restored by XGBoost's own model parser (not pickle)
    "xgboost.sklearn.XGBClassifier",  # XGBoost's scikit-learn wrapper
]


class ModelStoreError(RuntimeError):
    """Model files are missing, don't match the manifest, or can't be fetched."""


def stage_file(stage: int) -> Path:
    return SKOPS_DIR / f"stage{stage}.skops"


def range_file(stage: int, k: int) -> Path:
    return SKOPS_DIR / f"stage{stage}-range-{k:02d}.skops"


def read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise ModelStoreError(f"{MANIFEST_PATH.name} is missing: run the export first.")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def file_ok(path: Path, entry: dict) -> bool:
    return (
        path.exists()
        and path.stat().st_size == entry["bytes"]
        and integrity.sha256_of(path) == entry["sha256"]
    )


def available() -> bool:
    """True if every model file exists locally and matches the manifest."""
    try:
        files = read_manifest()["files"]
    except ModelStoreError:
        return False
    return all(file_ok(SKOPS_DIR / name, entry) for name, entry in files.items())


def _fetch(url: str, entry: dict, dest_dir: Path) -> Path:
    """Download url to a temporary file, enforcing size and SHA-256. Returns the temp path."""
    digest, size = hashlib.sha256(), 0
    fd, tmp = tempfile.mkstemp(dir=dest_dir, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=120) as r:
            while chunk := r.read(1 << 20):
                size += len(chunk)
                if size > entry["bytes"]:
                    raise ModelStoreError("Download larger than expected.")
                digest.update(chunk)
                out.write(chunk)
        if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
            raise ModelStoreError("Download does not match its recorded fingerprint. Refusing it.")
        return Path(tmp)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        os.remove(tmp)
        raise ModelStoreError(
            f"Couldn't download the model archive: {e.__class__.__name__}."
        ) from e
    except BaseException:
        os.remove(tmp)
        raise


def download() -> None:
    """Fetch the release archive, verify it, then extract and verify each listed file."""
    manifest = read_manifest()
    if available():
        return
    url = manifest["base_url"] + manifest["archive"]["name"]
    if not url.startswith("https://"):
        raise ModelStoreError("Model downloads must use HTTPS.")
    if manifest["archive"]["bytes"] > MAX_DOWNLOAD_BYTES:
        raise ModelStoreError("The model archive is larger than allowed.")
    SKOPS_DIR.mkdir(parents=True, exist_ok=True)
    archive = _fetch(url, manifest["archive"], SKOPS_DIR)
    try:
        with zipfile.ZipFile(archive) as zf:
            # Extract ONLY the names the manifest lists (never paths from the
            # archive itself, so a crafted entry like "../x" can't escape).
            for name, entry in manifest["files"].items():
                if Path(name).name != name:
                    raise ModelStoreError(f"Unexpected file name in manifest: {name!r}")
                target = SKOPS_DIR / name
                with zf.open(name) as src, open(target, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                if not file_ok(target, entry):
                    target.unlink()
                    raise ModelStoreError(f"{name} does not match its recorded fingerprint.")
    finally:
        archive.unlink(missing_ok=True)


def load_bundles() -> dict:
    """Verify every file, then load each stage with skops, trusting only TRUSTED_TYPES."""
    import skops.io as sio

    manifest = read_manifest()
    # Verify everything first, so nothing is loaded at all if any one file is wrong.
    for name, entry in manifest["files"].items():
        if not file_ok(SKOPS_DIR / name, entry):
            raise ModelStoreError(
                f"{name} is missing or doesn't match deploy/models.json. "
                "Run:  python -m cardiostage.model_store download"
            )
    bundles = {}
    for s in config.STAGES:
        bundle = sio.load(stage_file(s), trusted=TRUSTED_TYPES)
        n = manifest["replicas"][str(s)]
        bundle["uncertainty"].replicas_ = [
            sio.load(range_file(s, k), trusted=TRUSTED_TYPES) for k in range(n)
        ]
        bundles[s] = bundle
    return bundles


def export(base_url: str) -> dict:
    """Convert the (fingerprint-checked) joblib bundles to skops, pack them, write the manifest."""
    import skops.io as sio

    def dump(obj, path: Path) -> None:
        sio.dump(obj, path, compression=zipfile.ZIP_DEFLATED, compresslevel=6)
        untrusted = set(sio.get_untrusted_types(file=path)) - set(TRUSTED_TYPES)
        if untrusted:
            raise ModelStoreError(f"Unreviewed types in {path.name}: {sorted(untrusted)}")

    SKOPS_DIR.mkdir(parents=True, exist_ok=True)
    for old in SKOPS_DIR.glob("*.skops"):
        old.unlink()
    replicas = {}
    for s in config.STAGES:
        bundle = integrity.load(config.MODELS_DIR / f"stage{s}.joblib")
        ensemble = copy.copy(bundle["uncertainty"])  # shallow copy: original untouched
        copies, ensemble.replicas_ = ensemble.replicas_, []
        dump({**bundle, "uncertainty": ensemble}, stage_file(s))
        for k, replica in enumerate(copies):
            dump(replica, range_file(s, k))
        replicas[str(s)] = len(copies)
        print(f"stage {s}: main file + {len(copies)} range files", flush=True)

    files = {
        p.name: {"bytes": p.stat().st_size, "sha256": integrity.sha256_of(p)}
        for p in sorted(SKOPS_DIR.glob("*.skops"))
    }
    archive = config.MODELS_DIR / ARCHIVE_NAME
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
        for name in files:  # files are already compressed inside
            zf.write(SKOPS_DIR / name, arcname=name)
    manifest = {
        "about": "Fingerprints of the released skops model files (cardiostage.model_store).",
        "base_url": base_url,
        "archive": {
            "name": ARCHIVE_NAME,
            "bytes": archive.stat().st_size,
            "sha256": integrity.sha256_of(archive),
        },
        "replicas": replicas,
        "files": files,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"archive: {archive} ({archive.stat().st_size / 1e6:.1f} MB)", flush=True)
    return manifest


def main(argv: list) -> None:
    command = argv[0] if argv else "verify"
    if command == "export":
        export(argv[1] if len(argv) > 1 else read_manifest()["base_url"])
    elif command == "download":
        download()
        print("model files downloaded and verified")
    elif command == "verify":
        print("all model files match the manifest" if available() else "missing or mismatched")
    else:
        sys.exit(f"unknown command: {command}")


if __name__ == "__main__":
    main(sys.argv[1:])
