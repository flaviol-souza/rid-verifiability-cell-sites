"""Operator de-identification for everything that leaves the analysis (figures, frozen numbers, paper macros).

The mapping is private: it lives either in the config (`presentation.operator_alias`) or, for a public repository, in a
git-ignored file named by `presentation_file` (e.g. experiments/configs/local/presentation.yaml). Raw operator names
stay in the internal tables; figures show "Operator A" and frozen keys use "opA".
"""


def load_alias(cfg: dict, root=None) -> dict:
    pres = cfg.get("presentation") or {}
    if not pres and cfg.get("presentation_file") and root is not None:
        import yaml
        from pathlib import Path
        f = Path(root) / cfg["presentation_file"]
        if f.exists():
            pres = (yaml.safe_load(f.read_text()) or {}).get("presentation") or {}
    return dict(pres.get("operator_alias") or {})


def sanitize(text: str, alias: dict, style: str = "label") -> str:
    """Replace raw operator names in free text or paths (case-insensitive, not inside longer words)."""
    import re
    for raw, a in (alias or {}).items():
        rep = f"Operator {a}" if style == "label" else f"op{a}"
        text = re.sub(rf"(?<![A-Za-z]){re.escape(raw)}(?![A-Za-z])", rep, text, flags=re.I)
    return text


def check(alias: dict, operators) -> None:
    """An empty mapping means 'no de-identification'. A non-empty one must cover every operator and be one-to-one."""
    if not alias:
        return
    missing = sorted(set(operators) - set(alias) - {"consortium"})
    if missing:
        raise ValueError(f"presentation.operator_alias has no entry for {missing}")
    if len(set(alias.values())) != len(alias):
        raise ValueError("presentation.operator_alias must be one-to-one")


def label(scenario: str, alias: dict) -> str:
    alias = alias or {}
    if scenario == "consortium":
        return "consortium"
    return f"Operator {alias[scenario]}" if scenario in alias else scenario


def key(scenario: str, alias: dict) -> str:
    alias = alias or {}
    if scenario == "consortium":
        return "consortium"
    return f"op{alias[scenario]}" if scenario in alias else scenario
