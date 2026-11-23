"""
Tests for cardiostage.model_store: released skops model files are used only
if they match deploy/models.json, and only reviewed types are trusted.
"""

import hashlib
import io
import json
import zipfile

import pytest

from cardiostage import config, model_store


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_archive(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def fake_store(tmp_path, monkeypatch):
    """A temporary skops folder, a fake release archive and a manifest describing them."""
    files = {f"stage{s}.skops": f"model-{s}".encode() * 100 for s in config.STAGES}
    archive = make_archive(files)
    manifest = {
        "base_url": "https://example.invalid/releases/download/models-v1/",
        "archive": {
            "name": model_store.ARCHIVE_NAME,
            "bytes": len(archive),
            "sha256": sha(archive),
        },
        "replicas": {str(s): 0 for s in config.STAGES},
        "files": {n: {"bytes": len(d), "sha256": sha(d)} for n, d in files.items()},
    }
    mpath = tmp_path / "models.json"
    mpath.write_text(json.dumps(manifest))
    monkeypatch.setattr(model_store, "MANIFEST_PATH", mpath)
    monkeypatch.setattr(model_store, "SKOPS_DIR", tmp_path / "skops")
    return {"files": files, "archive": archive, "manifest": manifest, "path": mpath}


def serve(monkeypatch, payload: bytes):
    """Replace urlopen with a fake that serves the given archive bytes."""
    requested = []

    def fake_urlopen(url, timeout=None):
        requested.append(url)
        return io.BytesIO(payload)

    monkeypatch.setattr(model_store.urllib.request, "urlopen", fake_urlopen)
    return requested


def leftovers():
    return list(model_store.SKOPS_DIR.glob("*.part")) + list(model_store.SKOPS_DIR.glob("*.skops"))


def test_download_verifies_and_extracts(fake_store, monkeypatch):
    requested = serve(monkeypatch, fake_store["archive"])
    assert not model_store.available()
    model_store.download()
    assert model_store.available()
    assert requested == [
        "https://example.invalid/releases/download/models-v1/" + model_store.ARCHIVE_NAME
    ]
    assert not list(model_store.SKOPS_DIR.glob("*.part"))  # the archive itself isn't kept
    requested.clear()
    model_store.download()  # already present and verified: nothing fetched again
    assert requested == []


def test_tampered_archive_is_rejected_and_nothing_extracted(fake_store, monkeypatch):
    serve(monkeypatch, b"X" * len(fake_store["archive"]))  # same size, different bytes
    with pytest.raises(model_store.ModelStoreError, match="fingerprint"):
        model_store.download()
    assert leftovers() == []


def test_mismatched_file_inside_archive_is_rejected(fake_store, monkeypatch):
    m = fake_store["manifest"]
    m["files"]["stage2.skops"]["sha256"] = "0" * 64  # archive is fine, one member isn't
    fake_store["path"].write_text(json.dumps(m))
    serve(monkeypatch, fake_store["archive"])
    with pytest.raises(model_store.ModelStoreError, match="stage2.skops"):
        model_store.download()
    assert not model_store.stage_file(2).exists()


def test_oversized_download_is_rejected(fake_store, monkeypatch):
    serve(monkeypatch, fake_store["archive"] + b"extra")
    with pytest.raises(model_store.ModelStoreError, match="larger than expected"):
        model_store.download()
    assert leftovers() == []


def test_plain_http_is_refused(fake_store, monkeypatch):
    m = fake_store["manifest"]
    m["base_url"] = "http://example.invalid/"
    fake_store["path"].write_text(json.dumps(m))
    with pytest.raises(model_store.ModelStoreError, match="HTTPS"):
        model_store.download()


def test_path_traversal_names_are_refused(fake_store, monkeypatch):
    m = fake_store["manifest"]
    m["files"]["../evil.skops"] = {"bytes": 1, "sha256": "0" * 64}
    fake_store["path"].write_text(json.dumps(m))
    serve(monkeypatch, fake_store["archive"])
    with pytest.raises(model_store.ModelStoreError, match="Unexpected file name"):
        model_store.download()


def test_load_refuses_mismatched_local_file(fake_store, monkeypatch):
    serve(monkeypatch, fake_store["archive"])
    model_store.download()
    model_store.stage_file(3).write_bytes(b"tampered" * 100)
    with pytest.raises(model_store.ModelStoreError, match="doesn't match"):
        model_store.load_bundles()


def test_trusted_types_are_the_reviewed_list():
    """Changing what skops may load must be a deliberate, reviewed edit."""
    assert sorted(model_store.TRUSTED_TYPES) == sorted(
        [
            "cardiostage.uncertainty.NoveltyDetector",
            "cardiostage.uncertainty.SubsampleEnsemble",
            "numpy.dtype",
            "sklearn.tree._tree.Tree",
            "sklearn.calibration._CalibratedClassifier",
            "sklearn.calibration._SigmoidCalibration",
            "sklearn.model_selection._split.StratifiedKFold",
            "sklearn.utils._bunch.Bunch",
            "xgboost.core.Booster",
            "xgboost.sklearn.XGBClassifier",
        ]
    )
    assert not any("builtins" in t or "eval" in t or "os." in t for t in model_store.TRUSTED_TYPES)


@pytest.mark.skipif(
    not (
        model_store.available()
        and all((config.MODELS_DIR / f"stage{s}.joblib").exists() for s in config.STAGES)
    ),
    reason="needs both the trained joblib models and the exported skops files",
)
def test_skops_models_give_identical_results():
    """The public (skops) models must answer exactly like the trained originals."""
    import numpy as np

    from cardiostage import integrity
    from cardiostage.data import load_clean, split_cleveland
    from cardiostage.predictor import CardioStagePredictor

    train, _ = split_cleveland(load_clean())
    original = CardioStagePredictor(
        {s: integrity.load(config.MODELS_DIR / f"stage{s}.joblib") for s in config.STAGES}, train
    )
    safe = CardioStagePredictor(model_store.load_bundles(), train)
    for patient in train.sample(3, random_state=7).to_dict("records"):
        for s in config.STAGES:
            a, b = original.assess(patient, s), safe.assess(patient, s)
            assert (a.risk, a.range_low, a.range_high, a.zone, a.unusual) == (
                b.risk,
                b.range_low,
                b.range_high,
                b.zone,
                b.unusual,
            )
            assert np.array_equal(
                a.explanation.contribution.values, b.explanation.contribution.values
            )
