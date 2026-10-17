"""R1 — keyed pseudonyms for drone identifiers (BM-6)."""
import hashlib
import hmac
import os

import pandas as pd


class KeyMissingError(RuntimeError):
    pass


class PseudonymCollisionError(RuntimeError):
    pass


def load_key(env_var: str) -> bytes:
    value = os.environ.get(env_var)
    if not value:
        raise KeyMissingError(f"environment variable {env_var} is not set")
    try:
        return bytes.fromhex(value)
    except ValueError:
        return value.encode("utf-8")


def pseudonym(serial: str, key: bytes, prefix: str = "uas_", n_hex: int = 12) -> str:
    digest = hmac.new(key, str(serial).encode("utf-8"), hashlib.sha256).hexdigest()
    return prefix + digest[:n_hex]


def anonymize_ids(ids: pd.Series, key: bytes, prefix: str = "uas_", n_hex: int = 12) -> pd.Series:
    """Map every distinct id to its pseudonym; raise on collision. The mapping is never returned or stored."""
    distinct = pd.Series(ids.astype(str).unique())
    mapped = distinct.map(lambda s: pseudonym(s, key, prefix, n_hex))
    if mapped.duplicated().any():
        raise PseudonymCollisionError("two distinct identifiers map to the same pseudonym")
    lut = dict(zip(distinct, mapped))
    return ids.astype(str).map(lut)


def anonymize_flights(raw: pd.DataFrame, key: bytes, prefix: str = "uas_", n_hex: int = 12) -> pd.DataFrame:
    out = raw.copy()
    out["uas_id"] = anonymize_ids(out.pop("flight_id"), key, prefix, n_hex)
    return out[["uas_id"] + [c for c in out.columns if c != "uas_id"]]
