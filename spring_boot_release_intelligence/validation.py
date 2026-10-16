from __future__ import annotations

VALID_OUTCOMES = {"PASS", "FAIL", "UNAVAILABLE", "NOT_EXECUTED"}


def check(name: str, outcome: str, observed, expected, evidence: list[str], detail: str = "") -> dict:
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"invalid check outcome: {outcome}")
    return {"name": name, "outcome": outcome, "observed": observed,
            "expected": expected, "evidence": evidence, "detail": detail}


def equality_check(name: str, observed, expected, evidence: list[str]) -> dict:
    return check(name, "PASS" if observed == expected else "FAIL",
                 observed, expected, evidence)


def availability_check(name: str, observed, evidence: list[str], *, available=None) -> dict:
    is_available = bool(observed) if available is None else bool(available)
    return check(name, "PASS" if is_available else "UNAVAILABLE", observed,
                 "available", evidence)


def evaluate(approach: str, case: str, checks: list[dict], limitations: list[str]) -> dict:
    """Derive feasibility status exclusively from executed check outcomes."""
    outcomes = [item["outcome"] for item in checks]
    if not checks or "NOT_EXECUTED" in outcomes:
        status = "NOT_TESTED"
    elif "FAIL" in outcomes:
        status = "FAILED"
    elif all(value == "UNAVAILABLE" for value in outcomes):
        status = "NOT_SUPPORTED"
    elif "UNAVAILABLE" in outcomes:
        status = "PARTIALLY_PROVEN"
    elif all(value == "PASS" for value in outcomes):
        status = "PROVEN"
    else:
        status = "FAILED"
    return {"approach": approach, "case": case, "status": status,
            "checks": checks, "limitations": limitations}
