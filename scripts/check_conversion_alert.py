import argparse
import json
from pathlib import Path

import numpy as np

BOOKS = {
    "winamax_fr": "Winamax",
    "betclic_fr": "Betclic",
    "unibet_fr": "Unibet",
}
ISSUES = [(a, b) for a in ("1", "N", "2") for b in ("1", "N", "2")]
EPS = 1e-9


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assignments_for(n):
    total = n ** 9
    codes = np.arange(total, dtype=np.int64)
    assignments = np.empty((total, 9), dtype=np.uint8)
    factor = 1
    for j in range(9):
        assignments[:, j] = (codes // factor) % n
        factor *= n
    masks = [(assignments == bi) for bi in range(n)]
    return assignments, masks


def tier_from_min_util(values):
    tier = np.zeros(values.shape, dtype=np.int8)
    tier[values >= 0.90 - EPS] = 1
    tier[values >= 0.95 - EPS] = 2
    tier[values >= 0.98 - EPS] = 3
    return tier


def pair_weights(m1, m2, books):
    n = len(books)
    combined = np.empty((9, n), dtype=np.float64)
    weights = np.empty((9, n), dtype=np.float64)
    upper_sum = 0.0
    for j, (a, b) in enumerate(ISSUES):
        for bi, book in enumerate(books):
            odd = float(m1["books"][book][a]) * float(m2["books"][book][b])
            combined[j, bi] = odd
            weights[j, bi] = 1.0 / (odd - 1.0) if odd > 1.0 else np.inf
        best = float(np.min(weights[j]))
        if not np.isfinite(best):
            return None
        upper_sum += best
    return combined, weights, 100.0 / upper_sum


def choose_best_index(valid, tier, min_util, conversion, total_util, cash):
    idx = np.flatnonzero(valid)
    if idx.size == 0:
        return None

    max_tier = int(np.max(tier[idx]))
    idx = idx[tier[idx] == max_tier]

    if max_tier == 0:
        best = float(np.max(min_util[idx]))
        idx = idx[np.abs(min_util[idx] - best) <= EPS]

    best = float(np.max(conversion[idx]))
    idx = idx[np.abs(conversion[idx] - best) <= EPS]

    best = float(np.max(min_util[idx]))
    idx = idx[np.abs(min_util[idx] - best) <= EPS]

    best = float(np.max(total_util[idx]))
    idx = idx[np.abs(total_util[idx] - best) <= EPS]

    best = float(np.max(cash[idx]))
    idx = idx[np.abs(cash[idx] - best) <= EPS]
    return int(idx[0])


def optimize_pair(m1, m2, books, balances, assignments, masks, precomputed=None):
    if not all(book in m1.get("books", {}) and book in m2.get("books", {}) for book in books):
        return None

    pw = precomputed or pair_weights(m1, m2, books)
    if not pw:
        return None
    combined, weights, upper_conversion = pw

    selected = weights[np.arange(9)[None, :], assignments]
    totals = np.stack(
        [np.sum(np.where(masks[bi], selected, 0.0), axis=1) for bi in range(len(books))],
        axis=1,
    )

    valid = np.all(np.isfinite(totals), axis=1) & np.all(totals > 0, axis=1)
    if not np.any(valid):
        return None

    balance_array = np.array([balances[b] for b in books], dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        cash = np.min(balance_array[None, :] / totals, axis=1)
    coefficient_sum = np.sum(totals, axis=1)
    conversion = 100.0 / coefficient_sum
    spend = cash[:, None] * totals
    min_util = np.min(spend / balance_array[None, :], axis=1)
    total_balance = float(np.sum(balance_array))
    total_freebets = cash * coefficient_sum
    total_util = total_freebets / total_balance
    tier = tier_from_min_util(min_util)

    valid &= np.isfinite(cash) & (cash > 0) & np.isfinite(conversion)
    best_idx = choose_best_index(valid, tier, min_util, conversion, total_util, cash)
    if best_idx is None:
        return None

    assignment = assignments[best_idx]
    rows = []
    spend_by_book = {book: 0.0 for book in BOOKS}
    for j, (a, b) in enumerate(ISSUES):
        bi = int(assignment[j])
        book = books[bi]
        odd1 = float(m1["books"][book][a])
        odd2 = float(m2["books"][book][b])
        combined_odd = float(combined[j, bi])
        stake = float(cash[best_idx] / (combined_odd - 1.0))
        spend_by_book[book] += stake
        rows.append({
            "issue": f"{a}-{b}",
            "book": book,
            "odd1": odd1,
            "odd2": odd2,
            "combined_odd": combined_odd,
            "stake": stake,
        })

    return {
        "m1": m1,
        "m2": m2,
        "cash": float(cash[best_idx]),
        "total_freebets": float(total_freebets[best_idx]),
        "conversion": float(conversion[best_idx]),
        "min_util": float(min_util[best_idx]),
        "total_util": float(total_util[best_idx]),
        "tier": int(tier[best_idx]),
        "spend": spend_by_book,
        "rows": rows,
        "upper_conversion": float(upper_conversion),
    }


def is_better(candidate, best):
    if best is None:
        return True
    if candidate["tier"] != best["tier"]:
        return candidate["tier"] > best["tier"]
    if candidate["tier"] == 0 and abs(candidate["min_util"] - best["min_util"]) > EPS:
        return candidate["min_util"] > best["min_util"]
    if abs(candidate["conversion"] - best["conversion"]) > EPS:
        return candidate["conversion"] > best["conversion"]
    if abs(candidate["min_util"] - best["min_util"]) > EPS:
        return candidate["min_util"] > best["min_util"]
    if abs(candidate["total_util"] - best["total_util"]) > EPS:
        return candidate["total_util"] > best["total_util"]
    return candidate["cash"] > best["cash"]


def outcome_text(match, code):
    if code == "1":
        return f'{match["home"]} gagne'
    if code == "2":
        return f'{match["away"]} gagne'
    return f'{match["home"]} - {match["away"]} : nul'


def make_markdown(result, config, data):
    best = result["best"]
    threshold = float(config["threshold"])
    balances = config["balances"]
    level = result["level"]
    lines = [
        f'<!-- conversion-alert-key:{result["alert_key"]} -->',
        f'@{config.get("assignee", "adri-31")} **conversion ≥ {threshold:.0f} % détectée.**',
        "",
        f'### {best["conversion"]:.2f} % de conversion',
        "",
        f'- Cash garanti : **{best["cash"]:.2f} €**',
        f'- Freebets utilisés : **{best["total_freebets"]:.2f} €**',
        f'- Match 1 : **{best["m1"]["title"]}**',
        f'- Match 2 : **{best["m2"]["title"]}**',
        f'- Niveau d’alerte : **≥ {level} %**',
        f'- Données : **{data.get("generated_at") or "inconnues"}**',
        "",
        "### Répartition",
    ]
    for book, label in BOOKS.items():
        balance = float(balances.get(book, 0) or 0)
        if balance <= 0:
            continue
        used = float(best["spend"].get(book, 0) or 0)
        lines.append(f'- {label} : **{used:.2f} € / {balance:.2f} €**')

    lines.extend([
        "",
        "### 9 paris calculés",
        "",
        "| Pari | Book | Cote 1 | Cote 2 | Combiné | Freebet |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for row in best["rows"]:
        a, b = row["issue"].split("-")
        bet = f'{outcome_text(best["m1"], a)} + {outcome_text(best["m2"], b)}'
        lines.append(
            f'| {bet} | {BOOKS[row["book"]]} | {row["odd1"]:.2f} | {row["odd2"]:.2f} | '
            f'{row["combined_odd"]:.2f} | {row["stake"]:.2f} € |'
        )

    lines.extend([
        "",
        "**Avant de jouer : ouvre le site et vérifie manuellement les cotes. Si elles ont changé, utilise « Cotes différentes » pour rescanner et recalculer toute la meilleure combinaison.**",
        "",
        "Site : https://adri-31.github.io/conversion-fb/",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="site/data/odds.json")
    parser.add_argument("--config", default=".github/alert-config.json")
    parser.add_argument("--output", default="alert.json")
    parser.add_argument("--markdown", default="alert.md")
    args = parser.parse_args()

    data = load_json(args.data)
    config = load_json(args.config)
    balances = {b: max(0.0, float(config.get("balances", {}).get(b, 0) or 0)) for b in BOOKS}
    active_books = [b for b, value in balances.items() if value > 0]

    result = {
        "triggered": False,
        "reason": None,
        "generated_at": data.get("generated_at"),
        "threshold": float(config.get("threshold", 78.0)),
        "best": None,
        "alert_key": "",
        "title": "",
        "level": None,
    }

    if not config.get("enabled", True):
        result["reason"] = "alertes désactivées"
    elif not active_books:
        result["reason"] = "aucun solde actif"
    elif data.get("complete_scan") is False:
        result["reason"] = "scan incomplet"
    elif data.get("error"):
        result["reason"] = f'données invalides: {data.get("error")}'
    else:
        events = [
            e for e in data.get("events", [])
            if all(b in e.get("books", {}) for b in active_books)
        ]
        if len(events) < 2:
            result["reason"] = "pas assez de matchs communs"
        else:
            assignments, masks = assignments_for(len(active_books))
            pairs = []
            for i in range(len(events)):
                for j in range(i + 1, len(events)):
                    pw = pair_weights(events[i], events[j], active_books)
                    if pw:
                        pairs.append((float(pw[2]), i, j, pw))
            pairs.sort(key=lambda x: x[0], reverse=True)

            best = None
            for upper, i, j, pw in pairs:
                if best is not None and best["tier"] == 3 and upper <= best["conversion"] + EPS:
                    break
                candidate = optimize_pair(
                    events[i], events[j], active_books, balances, assignments, masks, pw
                )
                if candidate and is_better(candidate, best):
                    best = candidate

            result["best"] = best
            threshold = float(config.get("threshold", 78.0))
            strong = float(config.get("strong_threshold", 80.0))
            if best is None:
                result["reason"] = "aucune conversion exploitable"
            elif best["conversion"] + EPS < threshold:
                result["reason"] = f'meilleure conversion {best["conversion"]:.2f}% < {threshold:.2f}%'
            else:
                level = int(strong if best["conversion"] + EPS >= strong else threshold)
                pair_ids = sorted([
                    str(best["m1"].get("id") or best["m1"].get("title")),
                    str(best["m2"].get("id") or best["m2"].get("title")),
                ])
                result["triggered"] = True
                result["level"] = level
                result["alert_key"] = f'{level}:{pair_ids[0]}:{pair_ids[1]}'
                result["title"] = f'ALERTE conversion {best["conversion"]:.2f}% · {best["m1"]["title"]} + {best["m2"]["title"]}'

    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result["triggered"]:
        Path(args.markdown).write_text(make_markdown(result, config, data), encoding="utf-8")
    else:
        Path(args.markdown).write_text("", encoding="utf-8")
    print(json.dumps({
        "triggered": result["triggered"],
        "reason": result["reason"],
        "conversion": (result.get("best") or {}).get("conversion"),
        "alert_key": result.get("alert_key"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
