import re, itertools, unicodedata
import streamlit as st
from curl_cffi import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- INTERFACE ---
st.set_page_config(page_title="Convertisseur Freebet", page_icon="💶", layout="wide")
st.title("💶 Convertisseur Freebets : Wina & Betclic")
st.markdown("Transforme tes paris gratuits en argent réel sans risque.")

st.sidebar.header("💰 Tes Soldes")
MAX_WINA = st.sidebar.number_input("Solde Winamax (€)", value=135.0)
MAX_BETCLIC = st.sidebar.number_input("Solde Betclic (€)", value=55.0)

WINA_URLS = ["https://www.winamax.fr/paris-sportifs/sports/1/800000542", "https://www.winamax.fr/paris-sportifs/sports/1/7", "https://www.winamax.fr/paris-sportifs/sports/1/1", "https://www.winamax.fr/paris-sportifs/sports/1/32", "https://www.winamax.fr/paris-sportifs/sports/1/30", "https://www.winamax.fr/paris-sportifs/sports/1/31"]
BETCLIC_URLS = ["https://www.betclic.fr/football-s1/ligue-des-champions-c8", "https://www.betclic.fr/football-s1/ligue-europa-c3453", "https://www.betclic.fr/football-s1/ligue-1-mcdonald-s-c4", "https://www.betclic.fr/football-s1/angl-premier-league-c3", "https://www.betclic.fr/football-s1/espagne-liga-primera-c7", "https://www.betclic.fr/football-s1/allemagne-bundesliga-c5", "https://www.betclic.fr/football-s1/italie-serie-a-c6"]

def match_identique(t1, t2):
    def nettoyer(texte): return unicodedata.normalize('NFKD', texte).encode('ASCII', 'ignore').decode('utf-8').lower().strip()
    try:
        w_dom, w_ext = t1.split(' - ')
        b_dom, b_ext = t2.split(' - ')
        return (SequenceMatcher(None, nettoyer(w_dom), nettoyer(b_dom)).ratio() > 0.75 and SequenceMatcher(None, nettoyer(w_ext), nettoyer(b_ext)).ratio() > 0.75)
    except: return False

def fetch_url(url):
    try: return requests.get(url, impersonate="chrome120", timeout=10).text
    except: return ""

def wina_extract():
    matchs = {}
    with ThreadPoolExecutor(max_workers=6) as ex: pages = list(ex.map(fetch_url, WINA_URLS))
    for text in pages:
        odds = dict(re.findall(r'"(\d{8,})":(\d+\.\d+|\d+)', text))
        bets = re.findall(r'"betId":(\d+).*?"outcomes":\[(\d+),(\d+),(\d+)\]', text)
        map_p = {b[0]: [b[1], b[2], b[3]] for b in bets}
        for bid, titre in re.findall(r'"mainBetId":(\d+).*?"title":"(.*? - .*?)"', text):
            if bid in map_p and all(o in odds for o in map_p[bid]):
                c = [float(odds[o]) for o in map_p[bid]]
                if min(c) >= 1.50: matchs[titre] = {'1':c[0], 'N':c[1], '2':c[2]}
    return matchs

def betclic_extract():
    matchs = {}
    with ThreadPoolExecutor(max_workers=6) as ex: pages = list(ex.map(fetch_url, BETCLIC_URLS))
    for text in pages:
        chunks = re.split(r'"name":"([^"]+ - [^"]+)"', text)
        for i in range(1, len(chunks) - 1, 2):
            odds = re.findall(r'"odds":(\d+\.\d+|\d+)', chunks[i+1][:3000])
            if len(odds) >= 3:
                c = [float(odds[0]), float(odds[1]), float(odds[2])]
                if 1.01 < min(c) < 50: matchs[chunks[i]] = {'1':c[0], 'N':c[1], '2':c[2]}
    return matchs

if st.button("🔍 Chercher les meilleures cotes"):
    with st.spinner("Recherche des matchs en cours..."):
        wina, betclic = wina_extract(), betclic_extract()
        matchs_communs = [{'t': wt, 'w': wc, 'b': bc} for wt, wc in wina.items() for bt, bc in betclic.items() if match_identique(wt, bt)]
        
        st.write(f"✅ {len(matchs_communs)} matchs trouvés en commun.")

        if len(matchs_communs) >= 2:
            best_gain_net, best_duo = 0, None
            for m1, m2 in itertools.combinations(matchs_communs[:15], 2):
                issues = [('1','1'), ('1','N'), ('1','2'), ('N','1'), ('N','N'), ('N','2'), ('2','1'), ('2','N'), ('2','2')]
                pw_raw, pb_raw, temp_cg = 0, 0, []
                for i1, i2 in issues:
                    c_w, c_b = m1['w'][i1] * m2['w'][i2], m1['b'][i1] * m2['b'][i2]
                    if c_w >= c_b: pw_raw += 1 / (c_w - 1); temp_cg.append(('WINA', c_w, i1, i2))
                    else: pb_raw += 1 / (c_b - 1); temp_cg.append(('BETCLIC', c_b, i1, i2))
                
                sp = pw_raw + pb_raw
                if sp > 0:
                    budget_max = min(MAX_WINA / (pw_raw/sp) if pw_raw > 0 else float('inf'), MAX_BETCLIC / (pb_raw/sp) if pb_raw > 0 else float('inf'))
                    gain_net = budget_max / sp
                    if gain_net > best_gain_net: best_gain_net, best_duo = gain_net, (m1, m2, temp_cg, sp, budget_max, (1/sp)*100)

            if best_duo:
                m1, m2, cg, sp, budget, tx = best_duo
                st.success(f"💎 OPTION RENTABLE TROUVÉE")
                
                # --- AFFICHAGE CLAIR ET JOLI ---
                col1, col2, col3 = st.columns(3)
                col1.metric("Taux de Conversion", f"{tx:.2f}%")
                col2.metric("Gain Cash Garanti", f"{best_gain_net:.2f} €")
                col3.metric("Total Freebets Joués", f"{budget:.2f} €")
                
                st.markdown("---")
                st.subheader(f"⚽ {m1['t']} ➕ {m2['t']}")
                st.markdown("##### Voici les 9 tickets à placer :")
                
                # Grille 3x3 simple et robuste
                for r in range(0, 9, 3):
                    cols = st.columns(3)
                    for c in range(3):
                        bookie, cote, i1, i2 = cg[r + c]
                        mise = (1 / (cote - 1) / sp) * budget
                        with cols[c]:
                            st.info(f"**Issue [{i1}-{i2}]**\n\n🏦 {bookie}\n\n📈 Cote : **{cote:.2f}**\n\n💶 Mise : **{mise:.2f} €**")

            else: st.warning("Aucun duo rentable trouvé. Les cotes actuelles sont trop basses.")
        else: st.error("Besoin d'au moins 2 matchs communs. Les bookmakers sont peut-être vides à cette heure-ci.")
