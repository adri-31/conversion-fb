import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BOOKS = ("winamax_fr", "betclic_fr", "unibet_fr")
SPORTS = {
    "Ligue 1": "soccer_france_ligue_one",
    "Ligue 2": "soccer_france_ligue_two",
    "Premier League": "soccer_epl",
    "Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Champions League": "soccer_uefa_champs_league",
    "Europa League": "soccer_uefa_europa_league",
    "Conference League": "soccer_uefa_europa_conference_league",
}
OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "odds.json"
API_KEY = os.environ.get("THE_ODDS_API_KEY", "").strip()


def write(payload):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_event(event, label):
    home, away = event.get("home_team"), event.get("away_team")
    books = {}
    for bookmaker in event.get("bookmakers", []):
        key = bookmaker.get("key")
        if key not in BOOKS:
            continue
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = {o.get("name"): o.get("price") for o in market.get("outcomes", [])}
            if home in outcomes and away in outcomes and outcomes.get("Draw") is not None:
                try:
                    books[key] = {"1": float(outcomes[home]), "N": float(outcomes["Draw"]), "2": float(outcomes[away])}
                except (TypeError, ValueError):
                    pass
                break
    if not books:
        return None
    return {
        "id": event.get("id"),
        "sport": label,
        "sport_key": event.get("sport_key"),
        "time": event.get("commence_time"),
        "home": home,
        "away": away,
        "title": f"{home} - {away}",
        "books": books,
    }


def fetch_sport(label, key):
    params = urlencode({
        "apiKey": API_KEY,
        "bookmakers": ",".join(BOOKS),
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    })
    url = f"https://api.the-odds-api.com/v4/sports/{key}/odds?{params}"
    req = Request(url, headers={"User-Agent": "conversion-fb-github/1.0"})
    try:
        with urlopen(req, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
            quota = {
                "remaining": response.headers.get("x-requests-remaining"),
                "used": response.headers.get("x-requests-used"),
                "last": response.headers.get("x-requests-last"),
            }
            return body, quota, None
    except HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace")
        return [], {}, f"{label}: API {exc.code} · {detail}"
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], {}, f"{label}: {type(exc).__name__}"


def main():
    now = datetime.now(timezone.utc).isoformat()
    if not API_KEY:
        write({
            "generated_at": now,
            "events": [],
            "quota": {},
            "errors": [],
            "error": "clé API GitHub non configurée",
        })
        return

    events, errors, quota = [], [], {}
    for label, sport_key in SPORTS.items():
        raw, q, error = fetch_sport(label, sport_key)
        if q:
            quota = q
        if error:
            errors.append(error)
            continue
        for event in raw:
            normalized = normalize_event(event, label)
            if normalized:
                events.append(normalized)

    dedup = {}
    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        if event_id not in dedup:
            dedup[event_id] = event
        else:
            dedup[event_id]["books"].update(event["books"])
    events = sorted(dedup.values(), key=lambda e: e.get("time") or "9999")
    write({
        "generated_at": now,
        "events": events,
        "quota": quota,
        "errors": errors,
        "error": None if events else ("aucun match exploitable" if not errors else "récupération partielle ou impossible"),
    })
    print(f"Generated {len(events)} events; errors={len(errors)}; remaining={quota.get('remaining', '?')}")


if __name__ == "__main__":
    main()
