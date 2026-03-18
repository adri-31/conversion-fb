import re, itertools, unicodedata
import streamlit as st
from curl_cffi import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- 🤖 CONFIGURATION TELEGRAM BOT ---
TELEGRAM_TOKEN = "8588964695:AAGLFcpp1qmVlNS-wuXt38GHagPHI5mJy8q0"
TELEGRAM_CHAT_ID = "318551687"

def envoyer_alerte_telegram(message):
    if "8588" not in TELEGRAM_TOKEN: return 
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=5)
    except:
        pass

# --- INTERFACE ---
st.set_page_config(page_title="Convertisseur Freebet", page_icon="💶", layout="wide")
st.title("💶 Convertisseur Freebets : Wina & Betclic")
st.markdown("Optimisation en temps réel avec alerte Telegram (≥ 75%).")

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
    with st.spinner("Analyse en cours..."):
        wina_data = wina_extract()
        betclic_data = betclic_extract()
        matchs = [{'t': wt, 'w': wc, 'b': bc} for wt, wc in wina_data.items() for bt, bc in betclic_data.items() if match_identique(wt, bt)]
        st.write(f"✅ {len(matchs)} matchs trouvés en commun.")

        if len(matchs) >= 2:
            best_gn, best_d = 0, None
            # On limite à 15 matchs pour éviter que Streamlit ne rame trop
            for m1, m2 in itertools.combinations(matchs[:15], 2):
                issues = [('1','1'), ('1','N'), ('1','2'), ('N','1'), ('N','N'), ('N','2'), ('2','1'), ('2','N'), ('2','2')]
                for rep in itertools.product(['W', 'B'], repeat=9):
                    pw, pb, cg = 0, 0, []
                    for idx, (i1, i2) in enumerate(issues):
                        if rep[idx] == 'W':
                            cote = m1['w'][i1] * m2['w'][i2]
                            pw += 1/(cote-1); cg.append(('WINA', cote, i1, i2))
                        else:
                            cote = m1['b'][i1] * m2['b'][i2]
                            pb += 1/(cote-1); cg.append(('BETCLIC', cote, i1, i2))
                    
                    sp = pw + pb
                    if sp > 0:
                        bw, bb = pw/sp, pb/sp
                        # Calcul du budget max selon tes soldes
                        bud_w = MAX_WINA / bw if bw > 0 else float('inf')
                        bud_b = MAX_BETCLIC / bb if bb > 0 else float('inf')
                        bud = min(bud_w, bud_b)
                        gn = bud / sp
                        tx = (1 / sp) * 100
                        
                        if gn > best_gn:
                            best_gn, best_d = gn, (m1, m2, cg, sp, bud, tx)

            if best_d:
                m1, m2, cg, sp, bud, tx = best_d
                st.success(f"💎 OPTION TROUVÉE - Conversion: {tx:.2f}%")
                
                # Alerte Telegram si conversion top
                if tx >= 75.0:
                    msg = f"🚨 <b>{tx:.2f}%</b>\n⚽ {m1['t']} + {m2['t']}\n💰 Gain: {best_gn:.2f}€"
                    envoyer_alerte_telegram(msg)
                
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
        else:
            st.error("Pas assez de matchs communs trouvés.")
