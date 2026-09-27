import copy

from census.link import link_trial
from census.post import MAX_LEN, build_thread, x_length
from census.scope import classify
from census.tally import compute


def _classified(trials, bundle):
    out = []
    for t in copy.deepcopy(trials):
        t.update(classify(t))
        t["program"] = link_trial(t, bundle["programs"]) if t["in_scope"] else ""
        out.append(t)
    return out


def _row(census, pid):
    return next(r for r in census["programs"] if r["program"] == pid)


def test_seed_floor_without_trials(bundle):
    census = compute(bundle, [], "2026-09-28")
    # Neuralink 21 + NeuCyber 30 + Paradromics 1 + Neuracle 1; Axoft's 11 are unspecified and excluded.
    assert census["total_floor"] == 53
    assert _row(census, "axoft")["floor"] == 0
    assert census["other_range"] == [50, 254]


def test_floor_uses_registry_and_keeps_acute_separate(trials, bundle):
    census = compute(bundle, _classified(trials, bundle), "2026-09-28")
    assert _row(census, "synchron")["floor"] == 6 and _row(census, "synchron")["basis"] == "registry"
    assert _row(census, "braingate")["floor"] == 15
    assert _row(census, "neuralink")["floor"] == 21  # estimated enrollment never counts
    assert _row(census, "academic-other")["acute"] == 12 and _row(census, "academic-other")["floor"] == 0
    assert census["total_floor"] == 74


def test_larger_not_sum(trials, bundle):
    b = copy.deepcopy(bundle)
    b["counts"].append({"id": "t-synchron", "program": "synchron", "measure": "chronic_implanted", "value": 10,
                        "qualifier": "exact", "as_of": "2026-09-01", "tier": "B", "source_url": "https://example.com"})
    census = compute(b, _classified(trials, b), "2026-09-28")
    assert _row(census, "synchron")["floor"] == 10  # max(10, 6), not 16
    b["counts"][-1]["value"] = 4
    census = compute(b, _classified(trials, b), "2026-09-28")
    assert _row(census, "synchron")["floor"] == 6


def test_tier_d_never_counts(bundle):
    b = copy.deepcopy(bundle)
    b["counts"].append({"id": "t-d", "program": "stairmed", "measure": "chronic_implanted", "value": 500,
                        "qualifier": "exact", "as_of": "2026-09-01", "tier": "D", "source_url": "https://example.com"})
    assert compute(b, [], "2026-09-28")["total_floor"] == 53


def test_x_length_counts_urls_as_23():
    assert x_length("see https://example.com/a/very/long/path/that/goes/on") == len("see ") + 23


def test_thread_fits_x(trials, bundle):
    census = compute(bundle, _classified(trials, bundle), "2026-09-28")
    changes = {"first_run": False, "floor_before": 53, "floor_after": 74,
               "items": [{"kind": "new_trial", "title": "NCT9000000%d: a very long trial title " % i * 3} for i in range(6)]}
    posts = build_thread(census, changes, "https://jikjii.github.io/bci-census/", "https://github.com/jikjii/bci-census", "2026-09-28")
    assert posts[0].startswith("BCI Census, Sep 28, 2026: at least 74 people")
    assert all(x_length(p) <= MAX_LEN for p in posts)
    assert not any("•" in p for p in posts)


def _trial(nct, program, status, n, kind="ACTUAL", completion="", duration="chronic", **extra):
    return {"nct_id": nct, "program": program, "in_scope": True, "duration": duration, "status": status,
            "enrollment": n, "enrollment_type": kind, "completion_date": completion, **extra}


def test_registry_counts_current_trials_only(bundle):
    trials = [
        _trial("T1", "synchron", "ACTIVE_NOT_RECRUITING", 6),
        _trial("T2", "synchron", "COMPLETED", 5, completion="2022-01-09"),     # ended 4.7 years before: counted
        _trial("T3", "synchron", "COMPLETED", 9, completion="2019-06"),        # ended 7 years before: not counted
        _trial("T4", "synchron", "UNKNOWN", 7),                                # stale record: not counted
        _trial("T5", "synchron", "RECRUITING", 30, kind="ESTIMATED"),          # a target, not people
        _trial("T6", "synchron", "COMPLETED", 12, completion="2025-01", duration="acute"),
    ]
    row = _row(compute(bundle, trials, "2026-09-26"), "synchron")
    assert row["floor"] == 11 and row["registry_trials"] == ["T1", "T2"]
    assert row["acute"] == 12


def test_sourced_implanted_count_replaces_enrollment(bundle):
    trials = [_trial("T2", "synchron", "COMPLETED", 5, completion="2022-01-09", implanted=4),
              _trial("T1", "synchron", "ACTIVE_NOT_RECRUITING", 6)]
    assert _row(compute(bundle, trials, "2026-09-26"), "synchron")["floor"] == 10


def test_override_validation(bundle):
    from census.curated import validate

    b = copy.deepcopy(bundle)
    b["overrides"] = {"NCT1": {"implanted": 4, "reason": "paper says 4"}, "NCT2": {"program": "nope", "reason": "x"},
                      "NCT3": {"in_scope": False}}
    errors = "\n".join(validate(b))
    assert "NCT1 sets 'implanted' without a source_url" in errors
    assert "NCT2 points at unknown program" in errors
    assert "NCT3 needs a 'reason'" in errors
    assert not validate(bundle)
