const BOOKS = {
  winamax_fr: "Winamax",
  betclic_fr: "Betclic",
  unibet_fr: "Unibet",
};
const ISSUES = ["1", "N", "2"].flatMap(a => ["1", "N", "2"].map(b => [a, b]));
const els = {
  status: document.getElementById("dataStatus"),
  results: document.getElementById("results"),
  summary: document.getElementById("summary"),
  button: document.getElementById("calculateBtn"),
  progress: document.getElementById("progress"),
  wina: document.getElementById("balanceWinamax"),
  betclic: document.getElementById("balanceBetclic"),
  unibet: document.getElementById("balanceUnibet"),
};
let dataset = null;
const assignmentCache = new Map();

function money(v) { return `${Number(v).toFixed(2)} €`; }
function pct(v) { return `${Number(v).toFixed(2)} %`; }
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
}
function saveSettings() {
  localStorage.setItem("conversion-fb-v2", JSON.stringify({
    wina: els.wina.value,
    betclic: els.betclic.value,
    unibet: els.unibet.value,
  }));
}
function restoreSettings() {
  try {
    const s = JSON.parse(localStorage.getItem("conversion-fb-v2") || "null");
    if (!s) return;
    if (s.wina != null) els.wina.value = s.wina;
    if (s.betclic != null) els.betclic.value = s.betclic;
    if (s.unibet != null) els.unibet.value = s.unibet;
  } catch {}
}
function balances() {
  return {
    winamax_fr: Math.max(0, Number(els.wina.value) || 0),
    betclic_fr: Math.max(0, Number(els.betclic.value) || 0),
    unibet_fr: Math.max(0, Number(els.unibet.value) || 0),
  };
}
function activeBooks(bals) { return Object.keys(BOOKS).filter(b => bals[b] > 0); }

function assignmentsFor(n) {
  if (assignmentCache.has(n)) return assignmentCache.get(n);
  const total = Math.pow(n, 9);
  const data = new Uint8Array(total * 9);
  for (let code = 0; code < total; code++) {
    let x = code;
    const base = code * 9;
    for (let j = 0; j < 9; j++) {
      data[base + j] = x % n;
      x = Math.floor(x / n);
    }
  }
  const value = {total, data};
  assignmentCache.set(n, value);
  return value;
}

function utilizationTier(minUtil) {
  if (minUtil >= 0.98 - 1e-9) return 3;
  if (minUtil >= 0.95 - 1e-9) return 2;
  if (minUtil >= 0.90 - 1e-9) return 1;
  return 0;
}
function isBetter(candidate, best) {
  if (!best) return true;
  if (candidate.tier !== best.tier) return candidate.tier > best.tier;
  if (candidate.tier === 0 && Math.abs(candidate.minUtil - best.minUtil) > 1e-9) {
    return candidate.minUtil > best.minUtil;
  }
  if (Math.abs(candidate.conversion - best.conversion) > 1e-9) {
    return candidate.conversion > best.conversion;
  }
  if (Math.abs(candidate.minUtil - best.minUtil) > 1e-9) {
    return candidate.minUtil > best.minUtil;
  }
  if (Math.abs(candidate.totalUtil - best.totalUtil) > 1e-9) {
    return candidate.totalUtil > best.totalUtil;
  }
  return candidate.cash > best.cash;
}

function pairWeights(m1, m2, books) {
  const n = books.length;
  const combined = new Float64Array(9 * n);
  const weights = new Float64Array(9 * n);
  let upperWeightSum = 0;
  for (let j = 0; j < 9; j++) {
    const [a, b] = ISSUES[j];
    let bestWeight = Infinity;
    for (let bi = 0; bi < n; bi++) {
      const book = books[bi];
      const odd = Number(m1.books[book][a]) * Number(m2.books[book][b]);
      const idx = j * n + bi;
      combined[idx] = odd;
      const weight = odd > 1 ? 1 / (odd - 1) : Infinity;
      weights[idx] = weight;
      if (weight < bestWeight) bestWeight = weight;
    }
    if (!Number.isFinite(bestWeight)) return null;
    upperWeightSum += bestWeight;
  }
  return {combined, weights, upperConversion: 100 / upperWeightSum};
}

function optimizePair(m1, m2, bals, books, precomputed = null) {
  if (!books.every(b => m1.books[b] && m2.books[b])) return null;
  const n = books.length;
  const pw = precomputed || pairWeights(m1, m2, books);
  if (!pw) return null;
  const {combined, weights} = pw;
  const {total, data} = assignmentsFor(n);
  const totalBalance = books.reduce((s, b) => s + bals[b], 0);
  let best = null;

  for (let code = 0; code < total; code++) {
    const totals = new Float64Array(n);
    const base = code * 9;
    let valid = true;
    for (let j = 0; j < 9; j++) {
      const bi = data[base + j];
      const w = weights[j * n + bi];
      if (!Number.isFinite(w)) { valid = false; break; }
      totals[bi] += w;
    }
    if (!valid) continue;

    let cash = Infinity;
    let coefficientSum = 0;
    let everyBookUsed = true;
    for (let bi = 0; bi < n; bi++) {
      if (totals[bi] <= 0) { everyBookUsed = false; break; }
      cash = Math.min(cash, bals[books[bi]] / totals[bi]);
      coefficientSum += totals[bi];
    }
    if (!everyBookUsed || !Number.isFinite(cash) || cash <= 0 || coefficientSum <= 0) continue;

    let minUtil = 1;
    for (let bi = 0; bi < n; bi++) {
      minUtil = Math.min(minUtil, (cash * totals[bi]) / bals[books[bi]]);
    }
    const totalFreebets = cash * coefficientSum;
    const candidate = {
      code,
      cash,
      totalFreebets,
      conversion: 100 / coefficientSum,
      minUtil,
      totalUtil: totalFreebets / totalBalance,
      tier: utilizationTier(minUtil),
    };
    if (isBetter(candidate, best)) best = candidate;
  }

  if (!best) return null;
  const spend = Object.fromEntries(Object.keys(BOOKS).map(b => [b, 0]));
  const rows = [];
  const assignmentData = assignmentsFor(n).data;
  const base = best.code * 9;
  const updates = [];
  for (let j = 0; j < 9; j++) {
    const bi = assignmentData[base + j];
    const book = books[bi];
    const odd = combined[j * n + bi];
    const stake = best.cash / (odd - 1);
    spend[book] += stake;
    const u1 = m1.book_updates?.[book];
    const u2 = m2.book_updates?.[book];
    if (u1) updates.push(u1);
    if (u2) updates.push(u2);
    rows.push({issue: ISSUES[j], book, odd, stake});
  }
  const oldestUpdate = updates
    .map(x => new Date(x))
    .filter(x => !Number.isNaN(x.valueOf()))
    .sort((a, b) => a - b)[0] || null;
  return {...best, m1, m2, spend, rows, oldestUpdate};
}

function buildPairs(events, bals) {
  const books = activeBooks(bals);
  const validEvents = events.filter(e => books.every(b => e.books?.[b]));
  const pairs = [];
  for (let i = 0; i < validEvents.length; i++) {
    for (let j = i + 1; j < validEvents.length; j++) {
      const m1 = validEvents[i], m2 = validEvents[j];
      const pw = pairWeights(m1, m2, books);
      if (pw) pairs.push({m1, m2, pw});
    }
  }
  pairs.sort((a, b) => b.pw.upperConversion - a.pw.upperConversion);
  return {pairs, books, validEvents};
}

function outcomeText(match, code) {
  if (code === "1") return `${match.home} gagne`;
  if (code === "2") return `${match.away} gagne`;
  return `${match.home} - ${match.away} : nul`;
}
function ageText(date) {
  if (!date) return {text: "heure de mise à jour indisponible", cls: "warn"};
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes <= 10) return {text: `cotes utilisées mises à jour il y a ${minutes} min`, cls: "ok"};
  if (minutes <= 30) return {text: `cotes utilisées mises à jour il y a ${minutes} min · vérifie avant de jouer`, cls: "warn"};
  return {text: `cotes utilisées âgées de ${minutes} min · relance le scan avant de jouer`, cls: "warn"};
}

function renderSummary(totalEvents, validEvents, pairCount) {
  els.summary.classList.remove("hidden");
  els.summary.innerHTML = `
    <div class="metric"><small>Matchs disponibles</small><strong>${totalEvents}</strong></div>
    <div class="metric"><small>Matchs avec tous tes books actifs</small><strong>${validEvents}</strong></div>
    <div class="metric"><small>Paires vérifiées</small><strong>${pairCount}</strong></div>`;
}

function resultHtml(r, bals) {
  const bookRows = activeBooks(bals).map(b => {
    const left = Math.max(0, bals[b] - r.spend[b]);
    return `<div class="book"><strong>${BOOKS[b]}</strong>${money(r.spend[b])} / ${money(bals[b])}<br><span>reste ${money(left)}</span></div>`;
  }).join("");
  const rows = r.rows.map(row => {
    const [a,b] = row.issue;
    return `<tr><td>${escapeHtml(outcomeText(r.m1, a))}<br><span>+ ${escapeHtml(outcomeText(r.m2, b))}</span></td><td>${BOOKS[row.book]}</td><td class="odd">${row.odd.toFixed(2)}</td><td class="amount">${money(row.stake)}</td></tr>`;
  }).join("");
  const freshness = ageText(r.oldestUpdate);
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
      <div class="status ${freshness.cls}">${freshness.text}</div>
      <h3>Répartition</h3><div class="book-spend">${bookRows}</div>
      <h3>9 paris à placer</h3>
      <div style="overflow:auto"><table><thead><tr><th>Pari</th><th>Book</th><th>Cote combinée</th><th>Freebet</th></tr></thead><tbody>${rows}</tbody></table></div>
    </div>
  </article>`;
}

async function calculate() {
  if (!dataset || !Array.isArray(dataset.events)) return;
  saveSettings();
  const bals = balances();
  const books = activeBooks(bals);
  if (!books.length) {
    els.results.innerHTML = `<div class="message">Ajoute au moins un montant supérieur à 0.</div>`;
    return;
  }

  const {pairs, validEvents} = buildPairs(dataset.events, bals);
  renderSummary(dataset.events.length, validEvents.length, pairs.length);
  if (!pairs.length) {
    els.results.innerHTML = `<div class="message">Aucune paire de matchs n'a les cotes nécessaires sur tous les bookmakers où tu as un solde.</div>`;
    return;
  }

  els.button.disabled = true;
  els.results.innerHTML = "";
  let best = null;
  let checked = 0;
  try {
    for (let p = 0; p < pairs.length; p++) {
      const pair = pairs[p];
      if (best?.tier === 3 && pair.pw.upperConversion <= best.conversion + 1e-9) break;
      const result = optimizePair(pair.m1, pair.m2, bals, books, pair.pw);
      checked++;
      if (result && isBetter(result, best)) best = result;
      if (checked % 5 === 0 || checked === pairs.length) {
        els.progress.textContent = `Vérification ${checked} / ${pairs.length} paires…`;
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    }
    els.progress.textContent = `${checked} paire(s) calculée(s) exactement${checked < pairs.length ? ` · ${pairs.length - checked} éliminée(s) mathématiquement` : ""}.`;
    els.results.innerHTML = best ? resultHtml(best, bals) : `<div class="message">Aucune conversion exploitable trouvée.</div>`;
  } finally {
    els.button.disabled = false;
    els.button.textContent = "Trouver la meilleure conversion";
  }
}

async function boot() {
  restoreSettings();
  try {
    const res = await fetch(`data/odds.json?t=${Date.now()}`, {cache:"no-store"});
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    dataset = await res.json();
    const generated = dataset.generated_at ? new Date(dataset.generated_at) : null;
    const dateText = generated && !Number.isNaN(generated.valueOf())
      ? generated.toLocaleString("fr-FR", {dateStyle:"short", timeStyle:"short"})
      : "inconnue";
    const remaining = dataset.quota?.remaining;
    if (dataset.error) {
      els.status.className = "status warn";
      els.status.textContent = `Cotes indisponibles · ${dataset.error}`;
    } else {
      els.status.className = dataset.complete_scan === false ? "status warn" : "status ok";
      const scan = dataset.sports_available ? ` · ${dataset.sports_scanned}/${dataset.sports_available} compétitions` : "";
      els.status.textContent = `Scan ${dateText}${scan}${remaining != null ? ` · quota ${remaining}` : ""}`;
    }
  } catch (err) {
    els.status.className = "status warn";
    els.status.textContent = `Impossible de charger les cotes : ${err.message}`;
    dataset = {events: []};
  }
}

els.button.addEventListener("click", calculate);
[els.wina, els.betclic, els.unibet].forEach(el => el.addEventListener("change", saveSettings));
boot();
