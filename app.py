import itertools
import os
from functools import lru_cache

import numpy as np
import requests
import streamlit as st

st.set_page_config(page_title="Conversion Freebets 3 Books", page_icon="💶", layout="wide")

BOOKS = {
    "winamax_fr": "Winamax",
    "betclic_fr": "Betclic",
    "unibet_fr": "Unibet",
}

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

ISSUES = [(a, b) for a in ("1", "N", "2") for b in ("1", "N", "2")]


def secret_or_env(name: str):
    value = os.getenv(name)
    try:
        value = st.secrets.get(name, value)
    except Exception:
        pass
    return value


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sport_odds(sport_key: str, api_key: str):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "bookmakers": ",".join(BOOKS),
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    response = requests.get(url, params=params, timeout=20)
    if response.status_code != 200:
        try:
            detail = response.json().get("message") or response.text[:250]
        except Exception:
            detail = response.text[:250]
        raise RuntimeError(f"API {response.status_code}: {detail}")
    return response.json(), {
        "remaining": response.headers.get("x-requests-remaining"),
        "used": response.headers.get("x-requests-used"),
    }


def market_to_1n2(event, bookmaker):
    home = event.get("home_team")
    away = event.get("away_team")
    for market in bookmaker.get("markets", []):
        if market.get("key") != "h2h":
            continue
        outcomes = {x.get("name"): x.get("price") for x in market.get("outcomes", [])}
        draw = outcomes.get("Draw")
        if home in outcomes and away in outcomes and draw is not None:
            try:
                return {
                    "1": float(outcomes[home]),
                    "N": float(draw),
                    "2": float(outcomes[away]),
                }
            except (TypeError, ValueError):
                return None
    return None


def normalize_events(raw_events):
    events = []
    for event in raw_events:
        books = {}
        for bookmaker in event.get("bookmakers", []):
            key = bookmaker.get("key")
            if key not in BOOKS:
                continue
            odds = market_to_1n2(event, bookmaker)
            if odds:
                books[key] = odds
        if books:
            events.append({
                "id": event.get("id"),
                "sport": event.get("sport_title") or event.get("sport_key"),
                "time": event.get("commence_time"),
                "home": event.get("home_team"),
                "away": event.get("away_team"),
                "title": f"{event.get('home_team')} - {event.get('away_team')}",
                "books": books,
            })
    return events


@lru_cache(maxsize=4)
def assignment_matrix(book_count: int):
    return np.asarray(list(itertools.product(range(book_count), repeat=9)), dtype=np.uint8)


def optimize_pair(m1, m2, balances, min_combined_odd):
    common_books = [
        b for b in BOOKS
        if balances.get(b, 0) > 0 and b in m1["books"] and b in m2["books"]
    ]
    if not common_books:
        return None

    n = len(common_books)
    assignments = assignment_matrix(n)
    weights = np.zeros((9, n), dtype=float)
    combined = np.zeros((9, n), dtype=float)

    for j, (i1, i2) in enumerate(ISSUES):
        for b_idx, book in enumerate(common_books):
            odd = m1["books"][book][i1] * m2["books"][book][i2]
            combined[j, b_idx] = odd
            if odd > 1.0:
                weights[j, b_idx] = 1.0 / (odd - 1.0)
            else:
                weights[j, b_idx] = np.inf

    valid = np.ones(assignments.shape[0], dtype=bool)
    totals = np.zeros((assignments.shape[0], n), dtype=float)

    for j in range(9):
        for b_idx in range(n):
            chosen = assignments[:, j] == b_idx
            valid &= (~chosen) | (combined[j, b_idx] >= min_combined_odd)
            totals[:, b_idx] += chosen * weights[j, b_idx]

    cash_limits = np.full_like(totals, np.inf, dtype=float)
    for b_idx, book in enumerate(common_books):
        used = totals[:, b_idx] > 0
        cash_limits[used, b_idx] = balances[book] / totals[used, b_idx]

    guaranteed_cash = np.min(cash_limits, axis=1)
    guaranteed_cash[~valid] = -1.0
    if guaranteed_cash.size == 0 or np.max(guaranteed_cash) <= 0:
        return None

    best_cash = float(np.max(guaranteed_cash))
    candidates = np.where(np.isclose(guaranteed_cash, best_cash, rtol=1e-10, atol=1e-10))[0]
    if len(candidates) > 1:
        total_weights = np.sum(totals[candidates], axis=1)
        idx = int(candidates[np.argmin(total_weights)])
    else:
        idx = int(candidates[0])

    cash = float(guaranteed_cash[idx])
    rows = []
    spend = {b: 0.0 for b in BOOKS}
    total_freebets = 0.0

    for j, (i1, i2) in enumerate(ISSUES):
        b_idx = int(assignments[idx, j])
        book = common_books[b_idx]
        odd = float(combined[j, b_idx])
        stake = cash / (odd - 1.0)
        spend[book] += stake
        total_freebets += stake
        rows.append({
            "issue": f"{i1}-{i2}",
            "book": book,
            "odd": odd,
            "stake": stake,
        })

    conversion = 100.0 * cash / total_freebets if total_freebets else 0.0
    unused = sum(max(0.0, balances[b] - spend[b]) for b in BOOKS)

    return {
        "m1": m1,
        "m2": m2,
        "cash": cash,
        "total_freebets": total_freebets,
        "conversion": conversion,
        "spend": spend,
        "unused": unused,
        "rows": rows,
        "books": common_books,
    }


def rank_pairs(events, balances, min_combined_odd, max_pairs_to_show=5):
    results = []
    for m1, m2 in itertools.combinations(events, 2):
        result = optimize_pair(m1, m2, balances, min_combined_odd)
        if result:
            results.append(result)
    results.sort(key=lambda x: (x["cash"], x["conversion"]), reverse=True)
    return results[:max_pairs_to_show]


st.title("💶 Convertisseur Freebets — Winamax + Betclic + Unibet")
st.caption("Moteur 1N2 sur 2 matchs : 9 issues couvertes, répartition automatique entre les 3 bookmakers.")

with st.sidebar:
    st.header("Soldes freebets")
    balances = {
        "winamax_fr": st.number_input("Winamax (€)", min_value=0.0, value=135.0, step=5.0),
        "betclic_fr": st.number_input("Betclic (€)", min_value=0.0, value=55.0, step=5.0),
        "unibet_fr": st.number_input("Unibet (€)", min_value=0.0, value=0.0, step=5.0),
    }

    st.divider()
    st.header("Recherche")
    selected_sports = st.multiselect(
        "Compétitions",
        options=list(SPORTS.keys()),
        default=list(SPORTS.keys()),
    )
    max_events = st.slider("Nombre max de matchs analysés", 6, 30, 18)
    min_combined_odd = st.number_input("Cote combinée minimale", min_value=1.01, value=1.50, step=0.05)

    api_key = secret_or_env("THE_ODDS_API_KEY")
    if not api_key:
        api_key = st.text_input("Clé The Odds API", type="password", help="À mettre idéalement dans les Secrets Streamlit.")

    st.caption("Les réponses API sont mises en cache 5 min pour préserver le quota.")

if not any(v > 0 for v in balances.values()):
    st.warning("Ajoute au moins un solde freebet dans la barre latérale.")
    st.stop()

if st.button("🔍 Chercher la meilleure conversion", type="primary", use_container_width=True):
    if not api_key:
        st.error("Clé The Odds API manquante. Ajoute THE_ODDS_API_KEY dans les Secrets Streamlit ou saisis-la dans la barre latérale.")
        st.stop()
    if not selected_sports:
        st.error("Sélectionne au moins une compétition.")
        st.stop()

    all_events = []
    errors = []
    quota = None

    with st.spinner("Récupération des cotes Winamax, Betclic et Unibet..."):
        for label in selected_sports:
            try:
                raw, headers = fetch_sport_odds(SPORTS[label], api_key)
                all_events.extend(normalize_events(raw))
                quota = headers
            except Exception as exc:
                errors.append(f"{label}: {exc}")

    dedup = {e["id"]: e for e in all_events if e.get("id")}
    events = list(dedup.values())
    events.sort(key=lambda e: e.get("time") or "9999")
    events = events[:max_events]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matchs analysés", len(events))
    c2.metric("Avec Winamax", sum("winamax_fr" in e["books"] for e in events))
    c3.metric("Avec Betclic", sum("betclic_fr" in e["books"] for e in events))
    c4.metric("Avec Unibet", sum("unibet_fr" in e["books"] for e in events))

    if quota and quota.get("remaining") is not None:
        st.caption(f"Quota API restant : {quota['remaining']} crédits · utilisés : {quota.get('used', '?')}")

    if errors:
        with st.expander(f"{len(errors)} erreur(s) API partielle(s)"):
            for error in errors:
                st.write(error)

    if len(events) < 2:
        st.error("Pas assez de matchs exploitables pour construire une combinaison de 2 matchs.")
        st.stop()

    with st.spinner("Optimisation des 9 issues et des 3 bookmakers..."):
        best = rank_pairs(events, balances, min_combined_odd, max_pairs_to_show=5)

    if not best:
        st.error("Aucune combinaison compatible avec les soldes et la cote minimale choisie.")
        st.stop()

    for rank, result in enumerate(best, 1):
        title = f"#{rank} — {result['m1']['title']} + {result['m2']['title']}"
        with st.expander(title, expanded=(rank == 1)):
            a, b, c = st.columns(3)
            a.metric("Cash garanti", f"{result['cash']:.2f} €")
            b.metric("Freebets utilisés", f"{result['total_freebets']:.2f} €")
            c.metric("Conversion", f"{result['conversion']:.2f} %")

            st.write("**Répartition par bookmaker**")
            cols = st.columns(3)
            for col, book in zip(cols, BOOKS):
                col.metric(BOOKS[book], f"{result['spend'][book]:.2f} €", f"solde {balances[book]:.2f} €")

            st.write("**9 tickets à placer**")
            for start in range(0, 9, 3):
                cols = st.columns(3)
                for offset in range(3):
                    row = result["rows"][start + offset]
                    cols[offset].info(
                        f"**Issue {row['issue']}**\n\n"
                        f"{BOOKS[row['book']]}\n\n"
                        f"Cote combinée : **{row['odd']:.2f}**\n\n"
                        f"Mise freebet : **{row['stake']:.2f} €**"
                    )

            st.caption("Calcul freebet : la mise n'est pas rendue ; seul le gain net du pari (cote − 1) est converti en cash.")
