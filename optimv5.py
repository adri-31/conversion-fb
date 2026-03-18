import re, itertools, unicodedata
import streamlit as st
from curl_cffi import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- 🤖 CONFIGURATION TELEGRAM BOT ---
# Remplace par tes vrais codes
TELEGRAM_TOKEN = "8588964695:AAGLFcpp1qmVlNS-wuXt38GHagPHI5mJy8q0"
TELEGRAM_CHAT_ID = "318551687"

def envoyer_alerte_telegram(message):
    # Sécurité : on n'envoie que si le token n'est pas celui par défaut
    if "8588" not in TELEGRAM_TOKEN:
        return 
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        # On utilise curl_cffi aussi pour l'envoi pour rester cohérent
        requests.post(url, data=payload, timeout=5)
    except:
        pass

# --- INTERFACE ---
st.set_page_config(page_title="Convertisseur Freebet", page_icon="💶", layout="wide")
st.title("💶 Convertisseur Freebets : Wina & Betclic")
st.markdown("Transforme tes paris gratuits en argent réel en respectant tes soldes. **Alerte Telegram activée (≥ 75%).**")

st.sidebar.header("💰 Tes Soldes")
MAX_WINA = st.sidebar.number_input("Solde Winamax (€)", value=135.0)
MAX_BETCLIC = st.sidebar.number_input("Solde Betclic (€)", value=55.0)

BUDGET_TOTAL_THEORIQUE = MAX_WINA + MAX_BETCLIC
st.sidebar.success(f"💶 Total à convertir : **{BUDGET_TOTAL_THEORIQUE:.2f} €**")

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

def extract_all_data():
    results = {'WINA': {}, 'BETCLIC': {}}
    url_list = [(s, u) for s, urls in [('WINA', WINA_URLS), ('BETCLIC', BETCLIC_URLS)] for u in urls]
    
    with ThreadPoolExecutor(max_workers=6) as ex:
        pages_raw = list(ex.map(fetch_url, [u for s, u in url_list]))
    
    # Séparation manuelle pour éviter les bugs de structure
    wina_pages = pages_raw[:6]
    betclic_pages = pages_raw[6:]

    for text in wina_pages:
        odds = dict(re.findall(r'"(\d{8,})":(\d+\.\
