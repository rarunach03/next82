"""Sanity checks on the freshly exported site data, before the refresh workflow commits it.

Catches a broken or partial export (missing or unreadable files, far fewer players than
usual, a stale build) that the tests alone might let through. Exits 1 with the reasons.

    python scripts/check_site_data.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "web" / "public" / "data"
MIN_PLAYERS = 300   # about 450-600 in a normal export


def problems() -> list[str]:
    found = []
    try:
        index = json.loads((DATA / "index.json").read_text())
    except (OSError, ValueError) as e:
        return [f"index.json: {e}"]
    meta, players = index.get("meta", {}), index.get("players", [])
    if len(players) < MIN_PLAYERS:
        found.append(f"index.json lists only {len(players)} players (expected at least {MIN_PLAYERS})")
    if len(index.get("teams", [])) != 30:
        found.append(f"index.json lists {len(index.get('teams', []))} teams, not 30")
    generated = datetime.fromisoformat(meta.get("generatedAt", "1970-01-01T00:00:00+00:00"))
    if generated.tzinfo is None or datetime.now(timezone.utc) - generated > timedelta(hours=1):
        found.append(f"index.json wasn't just generated (generatedAt {meta.get('generatedAt')})")
    missing = [p["id"] for p in players if not (DATA / "players" / f"{p['id']}.json").exists()]
    if missing:
        found.append(f"{len(missing)} players have no player file, e.g. {missing[:3]}")
    names = ["accuracy.json", "fantasy.json"] + (["games.json"] if meta.get("gameBeta") else [])
    for name in names:
        try:
            json.loads((DATA / name).read_text())
        except (OSError, ValueError) as e:
            found.append(f"{name}: {e}")
    return found


if __name__ == "__main__":
    issues = problems()
    for line in issues:
        print(f"Site data check failed: {line}")
    if issues:
        sys.exit(1)
    print("Site data check passed")
