#!/usr/bin/env python3
"""Denné agregáty z hodinových meraní.

Vytvára:
  data/stats/daily.csv  date,station_id,pollutant,n,mean,min,max  (len ukončené dni, UTC)
  data/index.json       zoznam dní, ktoré majú hodinové súbory
Súbory sa prepíšu len ak sa obsah zmenil, takže zbytočne nevznikajú commity.
"""
import csv
import io
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "data"))


def write_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    days = sorted(p.stem for p in (DATA / "hourly").glob("*.csv"))
    agg = defaultdict(list)
    for day in days:
        if day >= today:
            continue
        with open(DATA / "hourly" / f"{day}.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["value"] != "":
                    agg[(day, r["station_id"], r["pollutant"])].append(float(r["value"]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "station_id", "pollutant", "n", "mean", "min", "max"])
    for (day, sid, pol) in sorted(agg):
        v = agg[(day, sid, pol)]
        w.writerow([day, sid, pol, len(v), round(sum(v) / len(v), 2), min(v), max(v)])
    a = write_if_changed(DATA / "stats" / "daily.csv", buf.getvalue())
    idx = {"days": days, "first_day": days[0] if days else None, "last_day": days[-1] if days else None}
    b = write_if_changed(DATA / "index.json", json.dumps(idx, separators=(",", ":")) + "\n")
    print(f"Dni: {len(days)}, denných agregátov: {len(agg)}, zmena: {a or b}")


if __name__ == "__main__":
    main()
