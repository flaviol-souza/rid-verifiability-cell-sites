import pandas as pd
import pytest

from drs.data import anonymize, stage_a


def test_pseudonym_format_and_determinism():
    k = bytes.fromhex("11" * 32)
    p = anonymize.pseudonym("SERIAL_A", k)
    assert p.startswith("uas_") and len(p) == 4 + 12
    assert p == anonymize.pseudonym("SERIAL_A", k)
    assert p != anonymize.pseudonym("SERIAL_A", bytes.fromhex("22" * 32))   # keyed, not a plain hash


def test_missing_key_stops_before_any_output(workspace, monkeypatch):
    root, cfg = workspace
    monkeypatch.delenv(cfg["stage_a"]["hmac_key_env"])
    with pytest.raises(anonymize.KeyMissingError):
        stage_a.run(cfg, root)
    assert not (root / cfg["stage_a"]["paths"]["flights_anon"]).exists()
    assert not (root / cfg["stage_a"]["paths"]["interim_dir"]).exists()


def test_collision_is_an_error():
    ids = pd.Series([f"S{i}" for i in range(200)])
    with pytest.raises(anonymize.PseudonymCollisionError):
        anonymize.anonymize_ids(ids, b"k", n_hex=1)       # 16 buckets for 200 ids → guaranteed collision


def test_no_raw_identifier_leaks_into_published_file(workspace):
    root, cfg = workspace
    stage_a.run(cfg, root)
    raw = pd.read_csv(root / cfg["stage_a"]["paths"]["flights_raw"], dtype={"flight_id": str})
    published = (root / cfg["stage_a"]["paths"]["flights_anon"]).read_text()
    for serial in raw["flight_id"].unique():                # includes the literal 'encrypted'
        assert serial not in published
    assert "flight_id" not in published.splitlines()[0]


def test_published_file_has_drone_positions_only(workspace):
    from conftest import HOME_ALT, OPER_ALT
    root, cfg = workspace
    res = stage_a.run(cfg, root)
    pub = pd.read_csv(root / cfg["stage_a"]["paths"]["flights_anon"])
    assert list(pub.columns) == ["uas_id", "lon", "lat", "alt", "timestamp"]
    assert not pub["alt"].isin([HOME_ALT, HOME_ALT + 0.5, OPER_ALT]).any()      # no pilot/home rows
    assert not pub.duplicated(["uas_id", "timestamp"]).any()
    refs = pd.read_parquet(root / cfg["stage_a"]["paths"]["interim_dir"] / "ground_refs.parquet")
    assert set(refs["role"]) == {"pilot", "home", "ground_ref"}
    assert "alt" not in refs.columns


def test_publishing_other_roles_is_refused(workspace):
    root, cfg = workspace
    cfg["stage_a"]["publish_roles"] = ["drone", "pilot"]
    with pytest.raises(ValueError):
        stage_a.run(cfg, root)
