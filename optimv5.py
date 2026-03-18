import re, itertools, unicodedata
import streamlit as st
from curl_cffi import requests # Moteur unique pour tout
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- 🤖 CONFIGURATION TELEGRAM ---
TELEGRAM_TOKEN = "8588964695:AAGLFcpp1qmVlNS-wuXt38GHagPHI5mJy8q0"
TELEGRAM_CHAT_ID = "318551687"

def envoyer_alerte_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        # On utilise le moteur curl_cffi qui ne se fait pas bloquer
        requests.post(url, data=payload, timeout=5, impersonate="chrome120")
    except:
        pass

# --- INTERFACE ---
st.set_page_config(page_title="Convertisseur Freebet", page_icon="💶", layout="wide")
st.title("💶 Convertisseur Freebets : Wina & Betclic")
st.markdown("Moteur V4 original (Fiable) + Alertes Telegram.")

# Barre latérale
st.sidebar.header("💰 Tes Soldes")
MAX_WINA = st.sidebar.number_input("Solde Winamax (€)", value=135.0)
MAX_BETCLIC = st.sidebar.number_input("Solde Betclic (€)", value=55.0)

st.sidebar.divider()
st.sidebar.header("🧪 Test Connexion")
if st.sidebar.button("📲 Envoyer un Test Telegram"):
    envoyer_alerte_telegram("<b>✅ Test réussi !</b>\nTon application TITAN est bien connectée à ton iPhone.")
    st.sidebar.success("Message envoyé ! Vérifie Telegram.")

WINA_URLS = ["https://www.winamax.fr/paris-sportifs/sports/1/800000542", "https://www.winamax.fr/paris-sportifs/sports/1/7", "https://www.winamax.fr/paris-sportifs/sports/1/1", "https://www.winamax.fr/paris-sportifs/sports/1/32", "https://www.winamax.fr/paris-sportifs/sports/1/30", "https://www.winamax.fr/paris-sportifs/sports/1/31"]
BETCLIC_URLS = ["https://www.betclic.fr/football-s1/ligue-des-champions-c8", "https://www.betclic.fr/football-s1/ligue-europa-c3453", "https://www.betclic.fr/football-s1/ligue-1-mcdonald-s-c4", "https://www.betclic.fr/football-s1/angl-premier-league-c3", "https://www.betclic.fr/football-s1/espagne-liga-primera-c7", "https://www.betclic.fr/football-s1/allemagne-bundesliga-c5", "https://www.betclic.fr/football-s1/italie-serie-a-c6"]

# --- FONCTIONS MOTEUR V4 (NE PAS TOUCHER) ---
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
    with st.spinner("Recherche et calcul (Moteur V4)..."):
        wina, betclic = wina_extract(), betclic_extract()
        matchs_communs = [{'t': wt, 'w': wc, 'b': bc} for wt, wc in wina.items() for bt, bc in betclic.items() if match_identique(wt, bt)]
        
        st.write(f"✅ {len(matchs_communs)} matchs trouvés en commun.")

        if len(matchs_communs) >= 2:
            best_gain_net = 0
            best_duo = None
            
            for m1, m2 in itertools.combinations(matchs_communs[:15], 2):
                issues = [('1','1'), ('1','N'), ('1','2'), ('N','1'), ('N','N'), ('N','2'), ('2','1'), ('2','N'), ('2','2')]
                for repartition in itertools.product(['W', 'B'], repeat=9):
                    pw_raw, pb_raw, cg_list = 0, 0, []
                    for idx, (i1, i2) in enumerate(issues):
                        if repartition[idx] == 'W':
                            cote = m1['w'][i1] * m2['w'][i2]
                            pw_raw += 1 / (cote - 1); cg_list.append(('WINA', cote, i1, i2))
                        else:
                            cote = m1['b'][i1] * m2['b'][i2]
                            pb_raw += 1 / (cote - 1); cg_list.append(('BETCLIC', cote, i1, i2))
                    sp = pw_raw + pb_raw
                    if sp == 0: continue
                    prop_w, prop_b = pw_raw / sp, pb_raw / sp
                    limite_w = MAX_WINA / prop_w if prop_w > 0 else float('inf')
                    limite_b = MAX_BETCLIC / prop_b if prop_b > 0 else float('inf')
                    budget_max = min(limite_w, limite_b)
                    gain_net = budget_max / sp
                    tx = (1 / sp) * 100
                    if gain_net > best_gain_net:
                        best_gain_net, best_duo = gain_net, (m1, m2, cg_list, sp, budget_max, tx)

            if best_duo:
                m1, m2, cg, sp, budget, tx = best_duo
                st.success(f"💎 OPTION SÉCURISÉE TROUVÉE")
                
                # --- ALERTE AUTO SI > 75% ---
                if tx >= 75.0:
                    alerte = f"🚨 <b>PÉPITE {tx:.2f}%</b> 🚨\n{m1['t']} + {m2['t']}\nGain : {best_gain_net:.2f}€"
                    envoyer_alerte_telegram(alerte)

                col1, col2, col3 = st.columns(3)
                col1.metric("Conversion", f"{tx:.2f}%")
                col2.metric("Gain Net", f"{best_gain_net:.2f} €")
                col3.metric("Joué", f"{budget:.2f} €")
                
                st.subheader(f"⚽ {m1['t']} ➕ {m2['t']}")
                for r in range(0, 9, 3):
                    cols = st.columns(3)
                    for c in range(3):
                        book, cote, i1, i2 = cg[r+c]
                        mise = (1/(cote-1)/sp)*budget
                        cols[c].info(f"[{i1}-{i2}] {book}\nCote: {cote:.2f}\nMise: {mise:.2f}€")
        else: st.error("Besoin d'au moins 2 matchs communs.")
