"""Aggregate confidence scoring for OSINT findings.

Each finding has a per-source confidence (e.g. 0.85 for a 200 OK profile,
0.55 for a redirect, 0.4 for a regex extraction off a single page). The
overall identity confidence combines:
  - number of independent corroborating sources
  - per-source confidence
  - cross-channel signals (e.g. same handle on >2 platforms)

Returns a 0-100 integer score plus a label.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class Signal:
    weight: float        # 0..1
    independent_source: bool = True


def aggregate(signals: Iterable[Signal]) -> tuple[int, str]:
    sigs = list(signals)
    if not sigs:
        return 0, "none"
    # 1 - prod(1 - w_i) — classic noisy-OR over independent signals,
    # then average in dependent ones.
    indep = [s.weight for s in sigs if s.independent_source]
    dep = [s.weight for s in sigs if not s.independent_source]
    p = 1.0
    for w in indep:
        p *= (1 - max(0.0, min(1.0, w)))
    score = 1.0 - p
    if dep:
        score = (score + sum(dep) / len(dep)) / 2
    pct = int(round(score * 100))
    return pct, _label(pct)


def _label(pct: int) -> str:
    if pct >= 80:
        return "high"
    if pct >= 55:
        return "medium"
    if pct >= 25:
        return "low"
    return "weak"
