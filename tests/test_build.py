import json
import shutil

import pytest

from census import build, config
from census.sources.clinicaltrials import normalize_study

from conftest import FIXTURES, ROOT


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point every output path at a temp copy of the repo's curated data."""
    shutil.copytree(ROOT / "data" / "curated", tmp_path / "data" / "curated")
    for name, sub in {
        "DATA": "data", "CURATED": "data/curated", "LATEST": "data/latest",
        "SNAPSHOTS": "data/snapshots", "DOCS": "docs", "POSTS": "posts",
    }.items():
        monkeypatch.setattr(config, name, tmp_path / sub)
    return tmp_path


def test_offline_build_then_diff(sandbox):
    first = build.run(offline=True, as_of="2026-09-28")
    assert first["census"]["total_floor"] == 53
    assert first["changes"]["first_run"] is True
    page = (sandbox / "docs" / "index.html").read_text()
    assert "BCI Census" in page and ">53<" in page
    assert (sandbox / "posts" / "2026-09-28.md").exists()
    assert (sandbox / "data" / "snapshots" / "2026-09-28" / "census.json").exists()
    assert (sandbox / "docs" / "data" / "trials_all.csv").exists()

    # Simulate the first live pull landing in data/latest, then rebuild a week later.
    raw = json.loads((FIXTURES / "ctgov_studies.json").read_text())["studies"]
    latest = sandbox / "data" / "latest" / "trials_all.json"
    latest.write_text(json.dumps([normalize_study(s) for s in raw]))
    second = build.run(offline=True, as_of="2026-10-05")
    items = second["changes"]["items"]
    # Floor changes lead; the new trials are summarized, not listed as 4 separate "new trial" lines.
    assert [i["kind"] for i in items] == ["floor_change", "floor_change", "first_pull"]
    assert {i["title"] for i in items[:2]} == {"BrainGate 0 → 15", "Synchron 0 → 6"}
    assert items[2]["title"].startswith("4 implanted BCI trials")
    assert second["changes"]["floor_before"] == 53 and second["changes"]["floor_after"] == 74
    assert "Verified floor: 53 → 74." in second["posts"][1]

    # A week later one trial changes status and another appears.
    pulled = json.loads(latest.read_text())
    pulled[0]["status"] = "ACTIVE_NOT_RECRUITING"
    extra = dict(pulled[7], nct_id="NCT90000009", url="https://clinicaltrials.gov/study/NCT90000009")
    latest.write_text(json.dumps(pulled + [extra]))
    third = build.run(offline=True, as_of="2026-10-12")
    kinds = sorted(i["kind"] for i in third["changes"]["items"])
    assert kinds == ["floor_change", "new_trial", "status_change"]  # the new trial has actual enrollment

    # Snapshots keep only what the diff needs; the full trial text stays in data/latest.
    snap = json.loads((sandbox / "data" / "snapshots" / "2026-10-12" / "trials_all.json").read_text())
    assert "summary" not in snap[0] and "status" in snap[0]
    assert "summary" in json.loads(latest.read_text())[0]


def test_first_edition_is_a_launch_thread(sandbox):
    result = build.run(offline=True, as_of="2026-09-28")
    posts = result["posts"]
    assert posts[0].startswith("How many people are living with a brain-computer interface implant?")
    assert "Published counts run from 50 to 254." in posts[0] and "at least 53" in posts[0]
    assert any(p.startswith("Verified floor by program:\nNeuCyber (China): 30") for p in posts)
    assert posts[-1].startswith("Found an error")
