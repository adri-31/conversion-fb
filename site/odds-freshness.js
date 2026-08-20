const ACTIONS_URL = "https://github.com/adri-31/conversion-fb/actions/workflows/site.yml";
const MANUAL_POLL_MS = 10000;
const MANUAL_POLL_TIMEOUT_MS = 10 * 60 * 1000;
let manualLastBest = null;
let manualPollTimer = null;
let manualPollBusy = false;

function manualPairKey(r) {
  if (!r) return "";
  return [r.m1?.id || r.m1?.title, r.m2?.id || r.m2?.title].sort().join("|");
}

function manualMessage(text, cls = "warn") {
  const el = document.getElementById("oddsCheckMessage");
  if (!el) return;
  el.className = `odds-check-message status ${cls}`;
  el.innerHTML = text;
}

function manualOddsVerificationTable(r) {
  const usedBooks = [...new Set(r.rows.map(row => row.book))];
  const rows = [];
  for (const book of usedBooks) {
    for (const [label, match] of [["Match 1", r.m1], ["Match 2", r.m2]]) {
      const odds = match.books?.[book] || {};
      rows.push(`<tr>
        <td><strong>${BOOKS[book]}</strong></td>
        <td>${label} · ${escapeHtml(match.title)}</td>
        <td class="odd">${Number(odds["1"]).toFixed(2)}</td>
        <td class="odd">${Number(odds["N"]).toFixed(2)}</td>
        <td class="odd">${Number(odds["2"]).toFixed(2)}</td>
      </tr>`);
    }
  }
  return `<div style="overflow:auto"><table>
    <thead><tr><th>Book</th><th>Match</th><th>1</th><th>N</th><th>2</th></tr></thead>
    <tbody>${rows.join("")}</tbody>
  </table></div>`;
}

function resultHtml(r, bals) {
  manualLastBest = r;
  const bookRows = activeBooks(bals).map(b => {
    const left = Math.max(0, bals[b] - r.spend[b]);
    return `<div class="book"><strong>${BOOKS[b]}</strong>${money(r.spend[b])} / ${money(bals[b])}<br><span>reste ${money(left)}</span></div>`;
  }).join("");

  const rows = r.rows.map(row => {
    const [a, b] = row.issue;
    const odd1 = Number(r.m1.books?.[row.book]?.[a]);
    const odd2 = Number(r.m2.books?.[row.book]?.[b]);
    return `<tr>
      <td>${escapeHtml(outcomeText(r.m1, a))}<br><span>+ ${escapeHtml(outcomeText(r.m2, b))}</span></td>
      <td>${BOOKS[row.book]}</td>
      <td class="odd">${odd1.toFixed(2)}</td>
      <td class="odd">${odd2.toFixed(2)}</td>
      <td class="odd"><strong>${row.odd.toFixed(2)}</strong></td>
      <td class="amount">${money(row.stake)}</td>
    </tr>`;
  }).join("");

  const useText = r.tier === 3
    ? "Au moins 98 % de chaque solde actif est utilisé."
    : `Meilleure utilisation trouvée : au moins ${pct(100 * r.minUtil)} de chaque solde actif.`;

  return `<article class="result" style="padding:0">
    <div class="content">
      <div class="rank">MEILLEURE CONVERSION</div>
      <h2>${escapeHtml(r.m1.title)}<br>${escapeHtml(r.m2.title)}</h2>
      <div class="result-metrics">
        <div class="metric"><small>Cash garanti</small><strong>${money(r.cash)}</strong></div>
        <div class="metric"><small>Freebets utilisés</small><strong>${money(r.totalFreebets)}</strong></div>
        <div class="metric"><small>Taux de conversion</small><strong>${pct(r.conversion)}</strong></div>
      </div>
      <p>${useText}</p>
      <h3>Répartition</h3><div class="book-spend">${bookRows}</div>

      <h3>Cotes à vérifier sur les bookmakers</h3>
      <p class="muted">Compare ces cotes avec celles affichées maintenant sur Winamax, Betclic et/ou Unibet. C'est toi qui décides si elles correspondent.</p>
      ${manualOddsVerificationTable(r)}

      <h3>9 paris à placer</h3>
      <div style="overflow:auto"><table>
        <thead><tr><th>Pari</th><th>Book</th><th>Cote match 1</th><th>Cote match 2</th><th>Combiné</th><th>Freebet</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>

      <div class="odds-check">
        <strong>Les cotes correspondent-elles à celles des bookmakers ?</strong>
        <p>Si une seule cote importante a changé, demande une mise à jour : le moteur rescannera puis vérifiera à nouveau toute la liste des matchs.</p>
        <div class="odds-check-actions">
          <button type="button" class="odds-action odds-ok" data-odds-action="ok">Cotes OK</button>
          <button type="button" class="odds-action odds-ko" data-odds-action="ko">Cotes différentes</button>
        </div>
        <div id="oddsCheckMessage"></div>
      </div>
    </div>
  </article>`;
}

function manualComparison(previous, current) {
  if (!current) return "Nouveau scan terminé, mais aucune conversion exploitable n'a été trouvée.";
  if (!previous) {
    return `Nouveau scan terminé. Meilleure conversion recalculée : <strong>${pct(current.conversion)}</strong>. Vérifie les nouvelles cotes affichées.`;
  }
  const same = manualPairKey(previous) === manualPairKey(current);
  if (same) {
    return `Nouveau scan terminé : <strong>les mêmes deux matchs restent les meilleurs</strong>. Taux ${pct(previous.conversion)} → <strong>${pct(current.conversion)}</strong>. Vérifie maintenant les nouvelles cotes affichées.`;
  }
  return `Nouveau scan terminé : <strong>la meilleure combinaison a changé</strong>.<br>Nouvelle paire : ${escapeHtml(current.m1.title)} + ${escapeHtml(current.m2.title)} · <strong>${pct(current.conversion)}</strong>. Vérifie ces nouvelles cotes.`;
}

function stopManualPolling() {
  if (manualPollTimer) clearInterval(manualPollTimer);
  manualPollTimer = null;
  manualPollBusy = false;
}

function startManualPolling(previousGeneratedAt, previousBest) {
  stopManualPolling();
  const startedAt = Date.now();

  const poll = async () => {
    if (manualPollBusy) return;
    manualPollBusy = true;
    try {
      if (Date.now() - startedAt > MANUAL_POLL_TIMEOUT_MS) {
        stopManualPolling();
        manualMessage(`Aucun nouveau scan détecté après 10 minutes. <a href="${ACTIONS_URL}" target="_blank" rel="noopener">Ouvre GitHub Actions</a>, lance <strong>Run workflow</strong>, puis reviens ici.`, "warn");
        return;
      }

      const res = await fetch(`data/odds.json?manual=${Date.now()}`, {cache: "no-store"});
      if (!res.ok) return;
      const next = await res.json();
      const oldTs = previousGeneratedAt ? new Date(previousGeneratedAt).getTime() : 0;
      const newTs = next.generated_at ? new Date(next.generated_at).getTime() : 0;
      if (!newTs || newTs <= oldTs) return;

      stopManualPolling();
      dataset = next;
      manualMessage("Nouvelles cotes reçues. Recalcul de la meilleure conversion sur tous les matchs…", "warn");
      await boot();
      await calculate();
      const currentBest = manualLastBest;
      manualMessage(manualComparison(previousBest, currentBest), "ok");
    } catch (_) {
      // La prochaine tentative reprendra automatiquement.
    } finally {
      manualPollBusy = false;
    }
  };

  manualPollTimer = setInterval(poll, MANUAL_POLL_MS);
  poll();
}

els.results.addEventListener("click", event => {
  const button = event.target.closest("[data-odds-action]");
  if (!button) return;

  if (button.dataset.oddsAction === "ok") {
    stopManualPolling();
    const time = new Date().toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"});
    manualMessage(`<strong>Cotes validées par toi à ${time}.</strong> Tu peux utiliser cette combinaison tant que les cotes que tu vois ne baissent pas.`, "ok");
    return;
  }

  const previousBest = manualLastBest;
  const previousGeneratedAt = dataset?.generated_at || null;
  manualMessage(`J'ouvre GitHub Actions. Dans le nouvel onglet : <strong>Run workflow → Run workflow</strong>. Laisse cette page ouverte : dès que le nouveau scan est publié, elle recalculera automatiquement la meilleure paire.`, "warn");
  window.open(ACTIONS_URL, "_blank", "noopener");
  startManualPolling(previousGeneratedAt, previousBest);
});
