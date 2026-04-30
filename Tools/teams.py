"""
tools/teams.py

Shared team-resolution logic used by both the tools layer (namespaces.py)
and the monitor layer (monitor.py).

Exports:
  - TEAM_LABEL_KEYS          → config (from env, parsed once)
  - extract_teams(labels, annotations) → sorted deduplicated team list
"""

import os

# Single source of truth for which label/annotation keys encode team ownership.
# Override via env: TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"
TEAM_LABEL_KEYS: list[str] = [
    k.strip()
    for k in os.getenv(
        "TEAM_LABEL_KEYS",
        "team,owner,app.kubernetes.io/team",
    ).split(",")
    if k.strip()
]


def extract_teams(labels: dict, annotations: dict) -> list[str]:
    """
    Extract team names from a resource's labels and annotations.

    Checks every key in TEAM_LABEL_KEYS against both dicts.
    Values may be comma-separated ("team-a,team-b").

    Returns a sorted, deduplicated list. Empty list if nothing found.
    """
    teams: set[str] = set()
    for key in TEAM_LABEL_KEYS:
        for source in (labels, annotations):
            val = source.get(key, "") or ""
            for t in val.split(","):
                t = t.strip()
                if t:
                    teams.add(t)
    return sorted(teams)