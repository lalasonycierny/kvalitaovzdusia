#!/usr/bin/env python3
"""Archív meraní z verejného stavu kvalitaovzdusia.sk (/api/state).

Dohodnutý zdroj dát. Skript sa spúšťa každých 15 minút a ukladá:
  data/hourly/YYYY-MM-DD.csv   hodinové merania staníc SHMÚ (PM10, PM2.5, NO2, BZN, ...)
  data/meteo/YYYY-MM-DD.csv    10-minútové pozorovania meteo staníc SHMÚ
  data/weather/YYYY-MM-DD.csv  hodinový model počasia (Open-Meteo) pre oblasť rafinérie
  data/meta.json               zoznam staníc a súradnice
Zápis je idempotentný: rovnaký riadok sa nikdy nezdvojí, zmenená hodnota
(napr. unvalidated -> validovaná) sa prepíše.
"""
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = os.environ.get("STATE_URL", "https://kvalitaovzdusia.sk/api/state")
LOCAL = os.environ.get("STATE_FILE")  # len na testovanie: načíta súbor namiesto siete
DATA = Path(os.environ.get("DATA_DIR", "data"))
UA = "kvalitaovzdusia-archiv/1.0 (+https://github.com/lalasonycierny/kvalitaovzdusia)"

HOURLY_COLS = ["station_id", "pollutant", "time", "value", "quality"]
METEO_FIELDS = ["t", "tprz", "tlak", "vie_pr_rych", "vie_max_rych", "vie_pr_smer",
                "vlh_rel", "zglo", "zra_uhrn"]
METEO_COLS = ["station_id", "minute"] + METEO_FIELDS
WEATHER_FIELDS = ["speed", "direction", "speed80", "direction80", "temperature",
                  "temperature80", "humidity", "pressure", "cloud", "radiation",
                  "mixingHeight"]
WEATHER_COLS = ["time"] + WEATHER_FIELDS


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def s(v):
    return "" if v is None else str(v)


def fetch_state():
    if LOCAL:
        return json.loads(Path(LOCAL).read_text(encoding="utf-8"))
    last = None
    for attempt in range(4):
        try:
            r = requests.get(URL, timeout=60, headers={"User-Agent": UA, "Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    sys.exit(f"Nepodarilo sa načítať {URL}: {last}")


def upsert(path, cols, keycols, rows):
    """Pridá nové a prepíše zmenené riadky. Vráti (nové, zmenené)."""
    existing = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                existing[tuple(r[k] for k in keycols)] = r
    new = changed = 0
    for r in rows:
        k = tuple(r[c] for c in keycols)
        old = existing.get(k)
        if old is None:
            new += 1
        elif old != r:
            changed += 1
        else:
            continue
        existing[k] = r
    if new or changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            for k in sorted(existing):
                w.writerow(existing[k])
    return new, changed


def main():
    st = fetch_state()
    stations = st.get("stations")
    if not isinstance(stations, list) or not stations:
        sys.exit("Neočakávaná štruktúra odpovede: chýba zoznam 'stations'.")
    gen = int(st.get("generatedAt") or time.time())
    tot_new = tot_chg = 0

    # 1) hodinové merania staníc
    by_day = defaultdict(list)
    for stn in stations:
        for r in stn.get("data") or []:
            t = iso(r["time"])
            by_day[t[:10]].append({
                "station_id": s(stn["id"]), "pollutant": s(r["pollutant"]),
                "time": t, "value": s(r.get("value")), "quality": s(r.get("quality"))})
    for day, rows in by_day.items():
        n, c = upsert(DATA / "hourly" / f"{day}.csv", HOURLY_COLS,
                      ["station_id", "pollutant", "time"], rows)
        tot_new += n
        tot_chg += c

    # 2) 10-minútové meteo pozorovania (stránka ukazuje len posledné)
    by_day = defaultdict(list)
    for m in st.get("meteoStations") or []:
        o = m.get("observation")
        if not o or not o.get("minuta"):
            continue
        row = {"station_id": s(m["id"]), "minute": o["minuta"]}
        row.update({f: s(o.get(f)) for f in METEO_FIELDS})
        by_day[o["minuta"][:10]].append(row)
    for day, rows in by_day.items():
        n, c = upsert(DATA / "meteo" / f"{day}.csv", METEO_COLS, ["station_id", "minute"], rows)
        tot_new += n
        tot_chg += c

    # 3) model počasia: len hodiny staršie ako 2 h (nie predpoveď)
    by_day = defaultdict(list)
    for h in (st.get("weather") or {}).get("hours") or []:
        if h["time"] > gen - 7200:
            continue
        row = {"time": iso(h["time"])}
        row.update({f: s(h.get(f)) for f in WEATHER_FIELDS})
        by_day[row["time"][:10]].append(row)
    for day, rows in by_day.items():
        n, c = upsert(DATA / "weather" / f"{day}.csv", WEATHER_COLS, ["time"], rows)
        tot_new += n
        tot_chg += c

    # 4) metadáta (zapíše sa len pri zmene)
    w = st.get("weather") or {}
    meta = {
        "stations": [{"id": s(x["id"]), "name": x["name"], "lat": x["lat"], "lon": x["lon"],
                      "source": x.get("source"),
                      "pollutants": [p["name"] for p in x.get("pollutants") or []]}
                     for x in sorted(stations, key=lambda x: str(x["id"]))],
        "meteoStations": [{"id": s(x["id"]), "name": x["name"], "lat": x["lat"], "lon": x["lon"]}
                          for x in sorted(st.get("meteoStations") or [], key=lambda x: str(x["id"]))],
        "weatherPoint": {"lat": w.get("latitude"), "lon": w.get("longitude"), "source": w.get("source")},
    }
    mp = DATA / "meta.json"
    text = json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if not mp.exists() or mp.read_text(encoding="utf-8") != text:
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(text, encoding="utf-8")

    print(f"Stav z {iso(gen)}: nových riadkov {tot_new}, zmenených {tot_chg}")


if __name__ == "__main__":
    main()
