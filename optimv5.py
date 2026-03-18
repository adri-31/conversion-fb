import re, itertools, unicodedata
import streamlit as st
from curl_cffi import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- 🤖 CONFIGURATION TELEGRAM BOT ---
TELEGRAM_TOKEN = "8588964695:AAGLFcpp1qmVlNS-wuXt38GHagPHI5mJy_q0"
TELEGRAM_CHAT_ID = "318551687"

def envoyer_alerte_telegram(message):
    if "8588" not in TELEGRAM_TOKEN: return 
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try: requests.post(url, data=payload, timeout=5)
    except: pass

# --- INTERFACE ---
st.set_page_config(page_title="Convertisseur Freebet", page_icon="💶", layout="wide")
st.title("💶 Convertisseur Freebets : Wina & Betclic")
st.markdown("Optimisation en temps réel avec alerte Telegram (≥ 75%).")

st.sidebar.header("💰 Tes Soldes")
MAX_WINA = st.sidebar.number_input("Solde Winamax (€)", value=135.0)
MAX_BETCLIC = st.sidebar.number_input("Solde Betclic (€)", value=55.0)

BUDGET_TOTAL = MAX_WINA + MAX_BETCLIC
st.sidebar.success(f"💶 Total à convertir : **{BUDGET_TOTAL:.2f} €**")

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

def extract_all():
    res = {'WINA': {}, 'BETCLIC': {}}
    with ThreadPoolExecutor(max_workers=6) as ex:
        w_pages = list(ex.map(fetch_url, WINA_URLS))
        b_pages = list(ex.map(fetch_url, BETCLIC_URLS))
    
    for text in w_pages:
        odds = dict(re.findall(r'"(\d{8,})":(\d+\.\d+|\d+)', text))
        bets = re.findall(r'"betId":(\d+).*?"outcomes":\[(\d+),(\d+),(\d+)\]', text)
        for bid, o1, o2, o3 in bets:
            for bid_t, titre in re.findall(r'"mainBetId":(\d+).*?"title":"(.*? - .*?)"', text):
                if bid == bid_t and all(x in odds for x in [o1, o2, o3]):
                    c = [float(odds[o1]), float(odds[o2]), float(odds[o3])]
                    if min(c) >= 1.5: res['WINA'][titre] = {'1':c[0], 'N':c[1], '2':c[2]}

    for text in b_pages:
        chunks = re.split(r'"name":"([^"]+ - [^"]+)"', text)
        for i in range(1, len(chunks)-1, 2):
            o = re.findall(r'"odds":(\d+\.\d+|\d+)', chunks[i+1][:3000])
            if len(o) >= 3:
                c = [float(o[0]), float(o[1]), float(o[2])]
                if 1.01 < min(c) < 50: res['BETCLIC'][chunks[i]] = {'1':c[0], 'N':c[1], '2':c[2]}
    return res

if st.button("🔍 Chercher les meilleures cotes"):
    with st.spinner("Analyse en cours..."):
        data = extract_all()
        matchs = [{'t': wt, 'w': wc, 'b': bc} for wt, wc in data['WINA'].items() for bt, bc in data['BETCLIC'].items() if match_identique(wt, bt)]
        st.write(f"✅ {len(matchs)} matchs synchronisés.")

        if len(matchs) >= 2:
            best_gn, best_d = 0, None
            for m1, m2 in itertools.combinations(matchs[:15], 2):
                issues = [('1','1'), ('1','N'), ('1','2'), ('N','1'), ('N','N'), ('N','2'), ('2','1'), ('2','N'), ('2','2')]
                for rep in itertools.product(['W', 'B'], repeat=9):
                    pw, pb, cg = 0, 0, []
                    for idx, (i1, i2) in enumerate(issues):
                        site = 'w' if rep[idx] == 'W' else 'b'
                        cote = m1[site][i1] * m2[site][i2]
                        if rep[idx] == 'W': pw += 1/(cote-1); cg.append(('WINA', cote, i1, i2))
                        else: pb += 1/(cote-1); cg.append(('BETCLIC', cote, i1, i2))
                    sp = pw + pb
                    if sp > 0:
                        bw, bb = pw/sp, pb/sp
                        bud = min(MAX_WINA/bw if bw>0 else 9999, MAX_BETCLIC/bb if bb>0 else 9999)
                        gn = bud/sp
                        if gn > best_gn: best_gn, best_d = gn, (m1, m2, cg, sp, bud, (1/sp)*100)

            if best_d:
                m1, m2, cg, sp, bud, tx = best_d
                st.success(f"💎 OPTION TROUVÉE - Conversion: {tx:.2f}%")
                if tx >= 75.0: envoyer_alerte_telegram(f"🚨 {tx:.2f}%\n{m1['t']}\n{m2['t']}\nGain: {best_gn:.2f}€")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Conversion", f"{tx:.2f}%")
                c2.metric("Gain Cash", f"{best_gn:.2f} €")
                c3.metric("Total Joué", f"{bud:.2f} €")
                
                st.subheader(f"⚽ {m1['t']} + {m2['t']}")
                for r in range(0, 9, 3):
                    cols = st.columns(3)
                    for c in range(3):
                        bk, ct, i1, i2 = cg[r+c]
                        ms = (1/(ct-1)/sp)*bud
                        cols[c].info(f"[{i1}-{i2}] {bk}\nCote: {ct:.2f}\nMise: {ms:.2f}€")
        else: st.error("Pas assez de matchs communs.")
