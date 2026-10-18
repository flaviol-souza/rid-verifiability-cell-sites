"""Operator de-identification for everything that leaves the analysis (figures, frozen numbers, paper macros).

The mapping lives in the config (`presentation.operator_alias`, e.g. {VIVO: A, CLARO: B, TIM: C}). Raw operator
names stay in the internal tables; figures show "Operator A" and frozen keys use "opA".
"""


def load_alias(cfg: dict) -> dict:
    return dict((cfg.get("presentation") or {}).get("operator_alias") or {})


def check(alias: dict, operators) -> None:
    """An empty mapping means 'no de-identification'. A non-empty one must cover every operator and be one-to-one."""
    if not alias:
        return
    missing = sorted(set(operators) - set(alias) - set(alias.values()) - {"consortium"})
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
