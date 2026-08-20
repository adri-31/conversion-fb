import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BOOKS = ("winamax_fr", "betclic_fr", "unibet_fr")
OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "odds.json"
API_KEY = os.environ.get("THE_ODDS_API_KEY", "").strip()
MIN_START_DELAY = timedelta(minutes=20)
QUOTA_RESERVE = 10


def write(payload):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def request_json(url, label):
    req = Request(url, headers={"User-Agent": "conversion-fb-github/2.0"})
    try:
        with urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            quota = {
                "remaining": response.headers.get("x-requests-remaining"),
                "used": response.headers.get("x-requests-used"),
                "last": response.headers.get("x-requests-last"),
            }
            return body, quota, None
    except HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace")
        return None, {}, f"{label}: API {exc.code} · {detail}"
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, {}, f"{label}: {type(exc).__name__}"


def active_soccer_sports():
    params = urlencode({"apiKey": API_KEY, "all": "false"})
    body, _, error = request_json(f"https://api.the-odds-api.com/v4/sports/?{params}", "sports")
    if error or not isinstance(body, list):
        return [], error or "sports: réponse invalide"

    sports = []
    for sport in body:
        key = sport.get("key", "")
        if not sport.get("active"):
            continue
        if sport.get("group") != "Soccer" and not key.startswith("soccer_"):
            continue
        if sport.get("has_outrights"):
            continue
        sports.append((sport.get("title") or key, key))
    sports.sort(key=lambda x: x[0].casefold())
    return sports, None


def normalize_event(event, label, now):
    start = parse_iso(event.get("commence_time"))
    if start is None or start <= now + MIN_START_DELAY:
        return None

    home, away = event.get("home_team"), event.get("away_team")
    if not home or not away:
        return None

    books = {}
    book_updates = {}
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
                    books[key] = {
                        "1": float(outcomes[home]),
                        "N": float(outcomes["Draw"]),
                        "2": float(outcomes[away]),
                    }
                    book_updates[key] = market.get("last_update") or bookmaker.get("last_update")
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
        "book_updates": book_updates,
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
    body, quota, error = request_json(url, label)
    return body if isinstance(body, list) else [], quota, error


def main():
    now = datetime.now(timezone.utc)
    generated_at = now.isoformat()
    if not API_KEY:
        write({
            "generated_at": generated_at,
            "events": [],
            "quota": {},
            "errors": [],
            "sports_scanned": 0,
            "sports_available": 0,
            "error": "clé API GitHub non configurée",
        })
        return

    sports, sports_error = active_soccer_sports()
    if sports_error:
        write({
            "generated_at": generated_at,
            "events": [],
            "quota": {},
            "errors": [sports_error],
            "sports_scanned": 0,
            "sports_available": 0,
            "error": "impossible de récupérer la liste des compétitions de football",
        })
        return

    events, errors, quota = [], [], {}
    scanned = 0
    stopped_for_quota = False

    for label, sport_key in sports:
        raw, q, error = fetch_sport(label, sport_key)
        scanned += 1
        if q:
            quota = q
        if error:
            errors.append(error)
        else:
            for event in raw:
                normalized = normalize_event(event, label, now)
                if normalized:
                    events.append(normalized)

        remaining = quota.get("remaining")
        if remaining is not None:
            try:
                if int(remaining) <= QUOTA_RESERVE:
                    stopped_for_quota = True
                    errors.append(f"Scan arrêté pour conserver {QUOTA_RESERVE} crédits API de sécurité.")
                    break
            except ValueError:
                pass

    dedup = {}
    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        if event_id not in dedup:
            dedup[event_id] = event
        else:
            dedup[event_id]["books"].update(event["books"])
            dedup[event_id]["book_updates"].update(event.get("book_updates", {}))

    events = sorted(dedup.values(), key=lambda e: e.get("time") or "9999")
    complete = scanned == len(sports) and not stopped_for_quota
    write({
        "generated_at": generated_at,
        "events": events,
        "quota": quota,
        "errors": errors,
        "sports_scanned": scanned,
        "sports_available": len(sports),
        "complete_scan": complete,
        "books": list(BOOKS),
        "error": None if events else ("aucun match exploitable" if not errors else "récupération partielle ou impossible"),
    })
    print(
        f"Generated {len(events)} events from {scanned}/{len(sports)} soccer competitions; "
        f"errors={len(errors)}; remaining={quota.get('remaining', '?')}"
    )


if __name__ == "__main__":
    main()
