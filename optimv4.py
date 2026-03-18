import re, itertools, unicodedata
import streamlit as st
from curl_cffi import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- ⚙️ CONFIGURATION DE L'APPLICATION ---
st.set_page_config(page_title="TITAN FB CONVERT", page_icon="💶", layout="wide")

st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .ticket-card { background-color: #1E1E1E; border: 2px solid #333; border-radius: 10px; padding: 15px; margin-bottom: 10px; }
    .stButton>button { width: 100%; border-radius: 20px; background-color: #FF4B4B; color: white; border: none; padding: 10px; font-size: 16px;}
    </style>
    """, unsafe_allow_html=True)

st.title("💶 Convertisseur Freebet Elite")
st.markdown("*Optimisation Wina/Betclic - Automatisée*")
st.divider()

# --- 💰 TES SOLDES ---
st.sidebar.header("💰 Tes Soldes Freebets")
MAX_WINA = st.sidebar.number_input("Solde Winamax (€)", value=135.0, step=5.0)
MAX_BETCLIC = st.sidebar.number_input("Solde Betclic (€)", value=55.0, step=5.0)

BUDGET_TOTAL_THEORIQUE = MAX_WINA + MAX_BETCLIC
st.sidebar.success(f"💶 Total à convertir : **{BUDGET_TOTAL_THEORIQUE:.2f} €**")
st.sidebar.divider()

URLS = {
    'WINA': ["https://www.winamax.fr/paris-sportifs/sports/1/800000542", "https://www.winamax.fr/paris-sportifs/sports/1/7", "https://www.winamax.fr/paris-sportifs/sports/1/1", "https://www.winamax.fr/paris-sportifs/sports/1/32"],
    'BETCLIC': ["https://www.betclic.fr/football-s1/ligue-des-champions-c8", "https://www.betclic.fr/football-s1/ligue-Europa-c3453", "https://www.betclic.fr/football-s1/ligue-1-mcdonald-s-c4", "https://www.betclic.fr/football-s1/angl-premier-league-c3"]
}

# LE RETOUR DE L'ANCIEN MATCHING SOUPLE (Celui qui trouve tout)
def match_identique(t1, t2):
    def nettoyer(texte): return unicodedata.normalize('NFKD', texte).encode('ASCII', 'ignore').decode('utf-8').lower().strip()
    try:
        w_dom, w_ext = t1.split(' - ')
        b_dom, b_ext = t2.split(' - ')
        return (SequenceMatcher(None, nettoyer(w_dom), nettoyer(b_dom)).ratio() > 0.75 and SequenceMatcher(None, nettoyer(w_ext), nettoyer(b_ext)).ratio() > 0.75)
    except: return False

def fetch_url(site_url):
    site, url = site_url
    try: return site, requests.get(url, impersonate="chrome120", timeout=10).text
    except: return site, ""

def extract_all_data():
    results = {'WINA': {}, 'BETCLIC': {}}
    url_list = [(s, u) for s, urls in URLS.items() for u in urls]
    with ThreadPoolExecutor(max_workers=8) as ex: pages = list(ex.map(fetch_url, url_list))
    
    for site, text in [p for p in pages if p[0] == 'WINA']:
        odds = dict(re.findall(r'"(\d{8,})":(\d+\.\d+|\d+)', text))
        bets = re.findall(r'"betId":(\d+).*?"outcomes":\[(\d+),(\d+),(\d+)\]', text)
        map_p = {b[0]: [b[1], b[2], b[3]] for b in bets}
        for bid, titre in re.findall(r'"mainBetId":(\d+).*?"title":"(.*? - .*?)"', text):
            if bid in map_p and all(o in odds for o in map_p[bid]):
                c = [float(odds[o]) for o in map_p[bid]]
                if min(c) >= 1.50: results['WINA'][titre] = {'1':c[0], 'N':c[1], '2':c[2]}
    
    for site, text in [p for p in pages if p[0] == 'BETCLIC']:
        found = re.findall(r'"name":"([^"]+ - [^"]+)".*?"odds":\[(.*?\])', text)
        for name, odds_raw in found:
            o = re.findall(r'(\d+\.\d+|\d+)', odds_raw)
            if len(o) >= 3: 
                c = [float(o[0]), float(o[1]), float(o[2])]
                if 1.01 < min(c) < 50: results['BETCLIC'][name] = {'1':c[0], 'N':c[1], '2':c[2]}
    return results

# --- 🚀 MOTEUR PRINCIPAL ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("📊 CHERCHER LES MEILLEURES COTES"):
        with st.spinner("Comparaison des matchs en cours..."):
            data = extract_all_data()
            matchs_unifies = []
            
            # RETOUR AU CROISEMENT FIABLE
            for wt, wc in data['WINA'].items():
                for bt, bc in data['BETCLIC'].items():
                    if match_identique(wt, bt):
                        matchs_unifies.append({'t': wt, 'sites': {'WINA': wc, 'BETCLIC': bc}})
                        break
            
            st.session_state['matchs_unifies'] = matchs_unifies
            if len(matchs_unifies) > 0:
                st.success(f"✅ {len(matchs_unifies)} matchs trouvés en commun !")
            else:
                st.error("❌ Aucun match trouvé. Les bookmakers n'ont peut-être pas encore sorti les cotes.")

if 'matchs_unifies' in st.session_state and st.session_state['matchs_unifies']:
    best_results = []
    # On limite aux 15 premiers pour la vitesse de calcul sur iPhone
    for m1, m2 in itertools.combinations(st.session_state['matchs_unifies'][:15], 2):
        combos, sp_fb = [], 0
        for i1, i2 in itertools.product(['1', 'N', '2'], repeat=2):
            best_c, best_s = 0, ""
            for s in ['WINA', 'BETCLIC']:
                if s in m1['sites'] and s in m2['sites']:
                    c = m1['sites'][s][i1] * m2['sites'][s][i2]
                    if c > best_c: best_c, best_s = c, s
            if best_c > 1.2:
                sp_fb += 1 / (best_c - 1)
                combos.append({'res': f"{i1}-{i2}", 'cote': best_c, 'site': best_s})
        
        if len(combos) == 9:
            best_results.append({'m1': m1['t'], 'm2': m2['t'], 'conv': (1 / sp_fb) * 100, 'combos': combos, 'sp': sp_fb})

    best_results.sort(key=lambda x: x['conv'], reverse=True)

    if best_results:
        st.divider()
        st.subheader("💎 Top 3 des opportunités")
        
        for rank, top in enumerate(best_results[:3]):
            with st.expander(f"🏆 Option #{rank+1} - Conversion : {top['conv']:.2f}%", expanded=(rank == 0)):
                
                pw = sum(1/(c['cote']-1) for c in top['combos'] if c['site'] == 'WINA')
                pb = sum(1/(c['cote']-1) for c in top['combos'] if c['site'] == 'BETCLIC')
                
                budget_max_jouable = min(BUDGET_TOTAL_THEORIQUE, 
                                         MAX_WINA / (pw/top['sp']) if pw > 0 else float('inf'), 
                                         MAX_BETCLIC / (pb/top['sp']) if pb > 0 else float('inf'))
                
                c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
                c_kpi1.metric("Conversion Nette", f"{top['conv']:.2f}%")
                c_kpi2.metric("Gain Cash Garanti", f"{budget_max_jouable * (top['conv']/100):.2f} €")
                c_kpi3.metric("Freebets Utilisés", f"{budget_max_jouable:.2f} €")
                st.divider()

                m1_n, m2_n = top['m1'].split(' - '), top['m2'].split(' - ')
                c_m1, c_m2, c_m3 = st.columns([1, 0.3, 1])
                with c_m1: st.markdown(f"<p class='big-font' style='text-align:right;'>{m1_n[0]}<br>{m1_n[1]}</p>", unsafe_allow_html=True)
                with c_m2: st.markdown("<p style='text-align:center; font-size:30px;'>+</p>", unsafe_allow_html=True)
                with c_m3: st.markdown(f"<p class='big-font' style='text-align:left;'>{m2_n[0]}<br>{m2_n[1]}</p>", unsafe_allow_html=True)

                st.markdown("##### 📝 Tes 9 tickets à placer :")
                for r in range(3):
                    cols = st.columns(3)
                    for c in range(3):
                        ticket = top['combos'][r * 3 + c]
                        mise = ((1 / (ticket['cote'] - 1)) / top['sp']) * budget_max_jouable
                        color = "#FF4B4B" if ticket['site'] == 'WINA' else "#FFFFFF"
                        cols[c].markdown(f"""
                        <div class='ticket-card'>
                            <p style='margin:0; text-align:center;'>ISSUE <b>[{ticket['res']}]</b></p>
                            <p style='margin:0; text-align:center; color:{color};'><b>{ticket['site']}</b></p>
                            <p style='margin:10px 0; text-align:center;'>Cote: <b>{ticket['cote']:.2f}</b></p>
                            <p style='margin:0; text-align:center; background-color:#333; padding:5px; border-radius:5px;'>Mise : <b>{mise:.2f} €</b></p>
                        </div>
                        """, unsafe_allow_html=True)
                
                if budget_max_jouable < BUDGET_TOTAL_THEORIQUE:
                    st.warning(f"⚠️ Afin de ne pas dépasser tes soldes actuels, le calcul s'est basé sur {budget_max_jouable:.2f}€ au lieu de {BUDGET_TOTAL_THEORIQUE:.2f}€.")
