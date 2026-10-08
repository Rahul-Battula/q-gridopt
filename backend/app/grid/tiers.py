"""Discrete battery levels (state of charge, MWh) used by the exact enumerator and the QUBO tiers.

The quantum model can only pick from a few battery levels per period. Each tier is one
choice of levels; qubit count = periods x bits per period (3 periods here).
    Q3  : {0, 20}           1 bit per period (0 -> 0 MWh, 1 -> 20 MWh), no one-hot penalty
    Q9  : {0, 20, 40}       one-hot, 3 bits per period
    Q18 : {0, 10, ..., 50}  one-hot, 6 bits per period
"""

TIERS: dict[str, tuple[float, ...]] = {
    "Q3": (0, 20),
    "Q9": (0, 20, 40),
    "Q18": (0, 10, 20, 30, 40, 50),
}

# "U" tiers add the gas unit on/off commitment to every period state, so unit commitment is part of
# what QAOA decides. State per period = (battery level, gas on/off), one-hot over 2L states, so
# qubits = periods x levels x 2 (Q3U: 12 qubits, Q9U: 18).
TIERS["Q3U"] = TIERS["Q3"]
TIERS["Q9U"] = TIERS["Q9"]
COMMIT_TIERS = frozenset({"Q3U", "Q9U"})


def is_commit_tier(tier: str | None) -> bool:
    return tier in COMMIT_TIERS
