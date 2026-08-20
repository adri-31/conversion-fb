const MAX_ODDS_AGE_MINUTES = 5;

function ageText(date) {
  if (!date || Number.isNaN(date.getTime())) {
    return {
      text: "COTES À METTRE À JOUR · heure de mise à jour indisponible",
      cls: "warn",
      fresh: false,
      minutes: null,
    };
  }
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  const exact = date.toLocaleString("fr-FR", {dateStyle: "short", timeStyle: "short"});
  if (minutes <= MAX_ODDS_AGE_MINUTES) {
    return {
      text: `COTES OK · plus ancienne cote : ${minutes} min · ${exact}`,
      cls: "ok",
      fresh: true,
      minutes,
    };
  }
  return {
    text: `COTES À METTRE À JOUR · plus ancienne cote : ${minutes} min · ${exact}`,
    cls: "warn",
    fresh: false,
    minutes,
  };
}

function resultHtml(r, bals) {
  const bookRows = activeBooks(bals).map(b => {
    const left = Math.max(0, bals[b] - r.spend[b]);
    return `<div class="book"><strong>${BOOKS[b]}</strong>${money(r.spend[b])} / ${money(bals[b])}<br><span>reste ${money(left)}</span></div>`;
  }).join("");

  const rows = r.rows.map(row => {
    const [a, b] = row.issue;
    const odd1 = Number(r.m1.books?.[row.book]?.[a]);
    const odd2 = Number(r.m2.books?.[row.book]?.[b]);
    const odd1Text = Number.isFinite(odd1) ? odd1.toFixed(2) : "—";
    const odd2Text = Number.isFinite(odd2) ? odd2.toFixed(2) : "—";
    return `<tr>
      <td>${escapeHtml(outcomeText(r.m1, a))}<br><span>+ ${escapeHtml(outcomeText(r.m2, b))}</span></td>
      <td>${BOOKS[row.book]}</td>
      <td class="odd">${odd1Text}</td>
      <td class="odd">${odd2Text}</td>
      <td class="odd"><strong>${row.odd.toFixed(2)}</strong></td>
      <td class="amount">${money(row.stake)}</td>
    </tr>`;
  }).join("");

  const freshness = ageText(r.oldestUpdate);
  const useText = r.tier === 3
    ? "Au moins 98 % de chaque solde actif est utilisé."
    : `Meilleure utilisation trouvée : au moins ${pct(100 * r.minUtil)} de chaque solde actif.`;
  const freshnessHelp = freshness.fresh
    ? "Les cotes affichées sont assez récentes pour valider la combinaison. Vérifie quand même qu'elles n'ont pas bougé au moment de placer chaque pari."
    : "Relance le workflow Conversion FB site dans GitHub Actions, attends la fin du scan, puis recharge cette page avant de placer les paris.";

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
      <div class="status ${freshness.cls}"><strong>${freshness.text}</strong><br><span>${freshnessHelp}</span></div>
      <h3>Répartition</h3><div class="book-spend">${bookRows}</div>
      <h3>9 paris à placer</h3>
      <div style="overflow:auto"><table>
        <thead><tr><th>Pari</th><th>Book</th><th>Cote match 1</th><th>Cote match 2</th><th>Combiné</th><th>Freebet</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>
  </article>`;
}
