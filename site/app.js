const BOOKS = {
  winamax_fr: "Winamax",
  betclic_fr: "Betclic",
  unibet_fr: "Unibet",
};
const ISSUES = ["1", "N", "2"].flatMap(a => ["1", "N", "2"].map(b => [a, b]));
const els = {
  status: document.getElementById("dataStatus"),
  filters: document.getElementById("sportFilters"),
  results: document.getElementById("results"),
  summary: document.getElementById("summary"),
  button: document.getElementById("calculateBtn"),
  wina: document.getElementById("balanceWinamax"),
  betclic: document.getElementById("balanceBetclic"),
  unibet: document.getElementById("balanceUnibet"),
  minOdd: document.getElementById("minOdd"),
  maxEvents: document.getElementById("maxEvents"),
  topCount: document.getElementById("topCount"),
};
let dataset = null;

function money(v) { return `${Number(v).toFixed(2)} €`; }
function pct(v) { return `${Number(v).toFixed(2)} %`; }
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
}
function saveSettings() {
  const checked = [...els.filters.querySelectorAll("input:checked")].map(x => x.value);
  localStorage.setItem("conversion-fb-settings", JSON.stringify({
    wina: els.wina.value, betclic: els.betclic.value, unibet: els.unibet.value,
    minOdd: els.minOdd.value, maxEvents: els.maxEvents.value, topCount: els.topCount.value,
    sports: checked,
  }));
}
function restoreSettings() {
  try {
    const s = JSON.parse(localStorage.getItem("conversion-fb-settings") || "null");
    if (!s) return null;
    if (s.wina != null) els.wina.value = s.wina;
    if (s.betclic != null) els.betclic.value = s.betclic;
    if (s.unibet != null) els.unibet.value = s.unibet;
    if (s.minOdd != null) els.minOdd.value = s.minOdd;
    if (s.maxEvents != null) els.maxEvents.value = s.maxEvents;
    if (s.topCount != null) els.topCount.value = s.topCount;
    return Array.isArray(s.sports) ? s.sports : null;
  } catch { return null; }
}
function renderFilters(events, stored) {
  const sports = [...new Set(events.map(e => e.sport).filter(Boolean))].sort((a,b) => a.localeCompare(b, "fr"));
  els.filters.innerHTML = sports.map(s => {
    const checked = !stored || stored.includes(s);
    return `<label class="chip"><input type="checkbox" value="${escapeHtml(s)}" ${checked ? "checked" : ""}>${escapeHtml(s)}</label>`;
  }).join("");
}
function selectedSports() { return new Set([...els.filters.querySelectorAll("input:checked")].map(x => x.value)); }
function balances() {
  return {
    winamax_fr: Math.max(0, Number(els.wina.value) || 0),
    betclic_fr: Math.max(0, Number(els.betclic.value) || 0),
    unibet_fr: Math.max(0, Number(els.unibet.value) || 0),
  };
}

function optimizePair(m1, m2, bals, minOdd) {
  const common = Object.keys(BOOKS).filter(b => bals[b] > 0 && m1.books[b] && m2.books[b]);
  if (!common.length) return null;
  const n = common.length;
  const combined = Array.from({length: 9}, () => Array(n).fill(0));
  const weights = Array.from({length: 9}, () => Array(n).fill(0));
  for (let j = 0; j < 9; j++) {
    const [a,b] = ISSUES[j];
    for (let bi = 0; bi < n; bi++) {
      const book = common[bi];
      const odd = Number(m1.books[book][a]) * Number(m2.books[book][b]);
      combined[j][bi] = odd;
      weights[j][bi] = odd > 1 ? 1 / (odd - 1) : Infinity;
    }
  }
  const totalAssignments = Math.pow(n, 9);
  let bestCash = -1, bestCode = -1, bestWeight = Infinity;
  for (let code = 0; code < totalAssignments; code++) {
    let x = code;
    const totals = Array(n).fill(0);
    let valid = true;
    for (let j = 0; j < 9; j++) {
      const bi = x % n;
      x = Math.floor(x / n);
      if (combined[j][bi] < minOdd || !Number.isFinite(weights[j][bi])) { valid = false; break; }
      totals[bi] += weights[j][bi];
    }
    if (!valid) continue;
    let cash = Infinity;
    let weightSum = 0;
    for (let bi = 0; bi < n; bi++) {
      if (totals[bi] > 0) {
        cash = Math.min(cash, bals[common[bi]] / totals[bi]);
        weightSum += totals[bi];
      }
    }
    if (!Number.isFinite(cash) || cash <= 0) continue;
    if (cash > bestCash + 1e-9 || (Math.abs(cash - bestCash) <= 1e-9 && weightSum < bestWeight)) {
      bestCash = cash; bestCode = code; bestWeight = weightSum;
    }
  }
  if (bestCode < 0) return null;
  const spend = Object.fromEntries(Object.keys(BOOKS).map(b => [b, 0]));
  const rows = [];
  let x = bestCode, totalFreebets = 0;
  for (let j = 0; j < 9; j++) {
    const bi = x % n;
    x = Math.floor(x / n);
    const book = common[bi];
    const odd = combined[j][bi];
    const stake = bestCash / (odd - 1);
    spend[book] += stake;
    totalFreebets += stake;
    rows.push({issue: `${ISSUES[j][0]}-${ISSUES[j][1]}`, book, odd, stake});
  }
  return {
    m1, m2, cash: bestCash, totalFreebets,
    conversion: totalFreebets ? 100 * bestCash / totalFreebets : 0,
    spend, rows,
  };
}

function rankPairs(events, bals, minOdd, limit) {
  const out = [];
  for (let i = 0; i < events.length; i++) {
    for (let j = i + 1; j < events.length; j++) {
      const r = optimizePair(events[i], events[j], bals, minOdd);
      if (r) out.push(r);
    }
  }
  out.sort((a,b) => (b.cash - a.cash) || (b.conversion - a.conversion));
  return out.slice(0, limit);
}

function renderSummary(events) {
  const count = b => events.filter(e => e.books && e.books[b]).length;
  els.summary.classList.remove("hidden");
  els.summary.innerHTML = `
    <div class="metric"><small>Matchs analysés</small><strong>${events.length}</strong></div>
    <div class="metric"><small>Avec Winamax</small><strong>${count("winamax_fr")}</strong></div>
    <div class="metric"><small>Avec Betclic</small><strong>${count("betclic_fr")}</strong></div>
    <div class="metric"><small>Avec Unibet</small><strong>${count("unibet_fr")}</strong></div>`;
}
function resultHtml(r, index) {
  const bals = balances();
  const spend = Object.keys(BOOKS).map(b => `<div class="book"><strong>${BOOKS[b]}</strong>${money(r.spend[b])}<br><span>solde ${money(bals[b])}</span></div>`).join("");
  const rows = r.rows.map(row => `<tr><td>${row.issue}</td><td>${BOOKS[row.book]}</td><td class="odd">${row.odd.toFixed(2)}</td><td class="amount">${money(row.stake)}</td></tr>`).join("");
  return `<details class="result" ${index === 0 ? "open" : ""}>
    <summary><div><div class="rank">#${index + 1}</div><div class="matches">${escapeHtml(r.m1.title)}<br>${escapeHtml(r.m2.title)}</div></div><div class="cash">${money(r.cash)} garantis</div></summary>
    <div class="content">
      <div class="result-metrics">
        <div class="metric"><small>Cash garanti</small><strong>${money(r.cash)}</strong></div>
        <div class="metric"><small>Freebets utilisés</small><strong>${money(r.totalFreebets)}</strong></div>
        <div class="metric"><small>Conversion</small><strong>${pct(r.conversion)}</strong></div>
      </div>
      <h3>Répartition</h3><div class="book-spend">${spend}</div>
      <h3>9 tickets à placer</h3>
      <div style="overflow:auto"><table><thead><tr><th>Issue</th><th>Book</th><th>Cote combinée</th><th>Mise freebet</th></tr></thead><tbody>${rows}</tbody></table></div>
    </div>
  </details>`;
}

function calculate() {
  if (!dataset || !Array.isArray(dataset.events)) return;
  saveSettings();
  const bals = balances();
  if (!Object.values(bals).some(v => v > 0)) {
    els.results.innerHTML = `<div class="message">Ajoute au moins un solde freebet supérieur à 0.</div>`; return;
  }
  const sports = selectedSports();
  const maxEvents = Math.max(2, Math.min(30, Number(els.maxEvents.value) || 18));
  const minOdd = Math.max(1.01, Number(els.minOdd.value) || 1.5);
  const topCount = Math.max(1, Math.min(10, Number(els.topCount.value) || 5));
  const events = dataset.events
    .filter(e => sports.size === 0 || sports.has(e.sport))
    .sort((a,b) => String(a.time || "9999").localeCompare(String(b.time || "9999")))
    .slice(0, maxEvents);
  renderSummary(events);
  if (events.length < 2) { els.results.innerHTML = `<div class="message">Pas assez de matchs exploitables avec les filtres actuels.</div>`; return; }
  els.button.disabled = true; els.button.textContent = "Optimisation en cours…";
  setTimeout(() => {
    try {
      const ranked = rankPairs(events, bals, minOdd, topCount);
      els.results.innerHTML = ranked.length ? ranked.map(resultHtml).join("") : `<div class="message">Aucune combinaison compatible avec les soldes et la cote minimale.</div>`;
    } finally {
      els.button.disabled = false; els.button.textContent = "Chercher la meilleure conversion";
    }
  }, 20);
}

async function boot() {
  const storedSports = restoreSettings();
  try {
    const res = await fetch(`data/odds.json?t=${Date.now()}`, {cache:"no-store"});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    dataset = await res.json();
    renderFilters(dataset.events || [], storedSports);
    const generated = dataset.generated_at ? new Date(dataset.generated_at) : null;
    const dateText = generated && !Number.isNaN(generated.valueOf()) ? generated.toLocaleString("fr-FR", {dateStyle:"short", timeStyle:"short"}) : "inconnue";
    if (dataset.error) {
      els.status.className = "status warn";
      els.status.textContent = `Cotes indisponibles · ${dataset.error}`;
    } else {
      const remaining = dataset.quota?.remaining;
      els.status.className = "status ok";
      els.status.textContent = `Cotes : ${dateText}${remaining != null ? ` · quota ${remaining}` : ""}`;
    }
  } catch (err) {
    els.status.className = "status warn";
    els.status.textContent = `Impossible de charger les cotes : ${err.message}`;
    dataset = {events: []};
    renderFilters([], storedSports);
  }
}

els.button.addEventListener("click", calculate);
[els.wina, els.betclic, els.unibet, els.minOdd, els.maxEvents, els.topCount].forEach(el => el.addEventListener("change", saveSettings));
els.filters.addEventListener("change", saveSettings);
boot();
