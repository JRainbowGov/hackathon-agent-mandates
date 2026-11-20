"""Pupil-level generation: a latent disadvantage factor with correlated census indicators."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

IDACI_TOP_SHARE = 0.20
BISECTION_ITERS = 60


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def calibrate_intercept(z: np.ndarray, target: float, lo: float = -30.0, hi: float = 30.0) -> float:
    """Find ``a`` such that ``mean(sigmoid(a + z)) == target``."""
    for _ in range(BISECTION_ITERS):
        mid = (lo + hi) / 2
        if sigmoid(mid + z).mean() < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def bernoulli_at_rate(rng: np.random.Generator, z: np.ndarray, rate: float) -> np.ndarray:
    """Bernoulli draws whose probability is ``sigmoid(a + z)`` with ``a`` calibrated so the mean is ``rate``."""
    if rate <= 0:
        return np.zeros(len(z), dtype=bool)
    a = calibrate_intercept(z, rate)
    return rng.random(len(z)) < sigmoid(a + z)


def generate_pupils(rng: np.random.Generator, n: int, cfg: dict[str, Any]) -> pd.DataFrame:
    """One row per pupil with the latent factor and the census / deprivation flags."""
    rates, lat = cfg["base_rates"], cfg["latent"]
    n_schools = int(cfg["schools"]["n"])
    school_idx = rng.integers(0, n_schools, n)
    school_effect = rng.standard_normal(n_schools) * float(cfg["schools"]["effect_sd"])
    u = rng.standard_normal(n) + school_effect[school_idx]

    idaci = sigmoid(lat["idaci"] * u + rng.standard_normal(n))
    idaci_top = idaci >= np.quantile(idaci, 1 - IDACI_TOP_SHARE)
    fsm = bernoulli_at_rate(rng, lat["fsm"] * u + lat["fsm_idaci_bonus"] * idaci_top, rates["fsm"])
    ever6_extra = bernoulli_at_rate(rng, lat["ever_fsm6"] * u, rates["ever_fsm6_extra"])
    ehcp = bernoulli_at_rate(rng, lat["ehcp"] * u, rates["ehcp"])
    sen_k = ~ehcp & bernoulli_at_rate(rng, lat["sen_support"] * u, rates["sen_support"] / (1 - rates["ehcp"]))
    in_care = bernoulli_at_rate(rng, lat["in_care"] * u, rates["in_care"])
    eal = rng.random(n) < rates["eal"]
    female = rng.random(n) < rates["female"]
    eth_codes = list(cfg["ethnic_group_major"].keys())
    eth_probs = np.array(list(cfg["ethnic_group_major"].values()), dtype=float)
    ethnic = rng.choice(eth_codes, n, p=eth_probs / eth_probs.sum())

    return pd.DataFrame(
        {
            "school_idx": school_idx,
            "latent_u": u,
            "Gender": np.where(female, "F", "M"),
            "EthnicGroupMajor": ethnic,
            "eal": eal,
            "fsm": fsm,
            "ever_fsm6": fsm | ever6_extra,
            "ehcp": ehcp,
            "sen_k": sen_k,
            "in_care": in_care,
            "idaci": idaci,
        }
    )
