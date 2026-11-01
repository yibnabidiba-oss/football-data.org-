"""Temporaire : enregistre les données ESPN du jour pour tester le direct."""
import json, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from leagues import LEAGUES
out = Path(__file__).resolve().parent.parent / "data" / "espn_sample"
out.mkdir(parents=True, exist_ok=True)
day = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y%m%d")
for code, info in LEAGUES.items():
    slug = info.get("espn")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={day}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            (out / f"{slug}.json").write_bytes(r.read())
            print(slug, "ok")
    except Exception as e:  # noqa: BLE001
        print(slug, e)
