import re, itertools, unicodedata, pandas as pd
import streamlit as st
from datetime import datetime
from curl_cffi import requests
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# --- ⚙️ CONFIGURATION DE L'APPLICATION (MODE MOBILE IPHONE) ---
st.set_page_config(page_title="TITAN FB CONVERT", page_icon="💶", layout="wide")

# Style CSS personnalisé pour l'esthétique et la lisibilité mobile
st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .ticket-card {
        background-color: #1E1E1E;
        border: 2px solid #333;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .gain-net { color: #00FF00; font-size: 24px; font-weight: bold; }
    .stButton>button { width: 100%; border-radius: 20px; background-color: #FF4B4B; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- 🌍 HEADER PRINCIPAL ET PARAMÈTRES ---
st.title("💶 Convertisseur Freebet Elite")
st.markdown("*Optimisation Syndicale Winamax & Betclic - Toulouse*")
st.divider()

# Barre latérale : configuration et plafonds
st.sidebar.header("⚙️ Configuration")
MONTANT_FREEBET_TOTAL = st.sidebar.number_input("💰 Montant Freebet à convertir (€)", value=100.0, step=10.0)
st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ Sécurités & Plafonds")
st.sidebar.markdown("*Vérifie tes plafonds de mise pour ne pas bloquer un ticket.*")
MAX_WINA = st.sidebar.number_input("Plafond Winamax (€)", value=135.0, help="Ton plafond de mise actuel")
MAX_BETCLIC = st.sidebar.number_input("Plafond Betclic (€)", value=55.0, help="Ton plafond de mise actuel")
st.sidebar.divider()

# --- 📡 NOUVEAU MOTEUR D'ASPIRATION (TURBO-FUSION) ---
URLS = {
    'WINA': [
        "https://www.winamax.fr/paris-sportifs/sports/1/800000542", # LDC / Europe
        "https://www.winamax.fr/paris-sportifs/sports/1/7",         # France
        "https://www.winamax.fr/paris-sportifs/sports/1/1",         # Angleterre
        "https://www.winamax.fr/paris-sportifs/sports/1/32"         # Espagne
    ],
    'BETCLIC': [
        "https://www.betclic.fr/football-s1/ligue-des-champions-c8", # LDC
        "https://www.betclic.fr/football-s1/ligue-Europa-c3453",     # Europa
        "https://www.betclic.fr/football-s1/ligue-1-mcdonald-s-c4",  # L1
        "https://www.betclic.fr/football-s1/angl-premier-league-c3"   # PL
    ]
}

def nettoyer_nom(texte):
    # Nettoyage ultra-agressif pour un matching parfait
    nom = unicodedata.normalize('NFKD', texte).encode('ASCII', 'ignore').decode('utf-8').lower()
    for word in ["fc", "stade", "olympique", "atletico", "atl.", "madrid", "united", "city", "vs", "-", "real", "hotspur", "bayer", "saint"]:
        nom = nom.replace(word, "")
    return "".join(nom.split())

def match_identique(t1, t2):
    # Matching double sécurité : Fuzzy + Exact sur noms nettoyés
    return SequenceMatcher(None, nettoyer_nom(t1), nettoyer_nom(t2)).ratio() > 0.73

def fetch_url(site_url):
    site, url = site_url
    try: return site, requests.get(url, impersonate="chrome120", timeout=8).text
    except: return site, ""

def extract_all_data():
    results = {'WINA': {}, 'BETCLIC': {}}
    url_list = [(s, u) for s, urls in URLS.items() for u in urls]
    
    with ThreadPoolExecutor(max_workers=8) as ex:
        pages = list(ex.map(fetch_url, url_list))
    
    # Parsing WINA
    for site, text in [p for p in pages if p[0] == 'WINA']:
        odds = dict(re.findall(r'"(\d{8,})":(\d+\.\d+|\d+)', text))
        bets = re.findall(r'"betId":(\d+).*?"outcomes":\[(\d+),(\d+),(\d+)\]', text)
        map_p = {b[0]: [b[1], b[2], b[3]] for b in bets}
        for bid, titre in re.findall(r'"mainBetId":(\d+).*?"title":"(.*? - .*?)"', text):
            if bid in map_p and all(o in odds for o in map_p[bid]):
                results['WINA'][titre] = {'1':float(odds[map_p[bid][0]]), 'N':float(odds[map_p[bid][1]]), '2':float(odds[map_p[bid][2]])}
    
    # Parsing BETCLIC
    for site, text in [p for p in pages if p[0] == 'BETCLIC']:
        found = re.findall(r'"name":"([^"]+ - [^"]+)".*?"odds":\[(.*?\])', text)
        for name, odds_raw in found:
            o = re.findall(r'(\d+\.\d+|\d+)', odds_raw)
            if len(o) >= 3: results['BETCLIC'][name] = {'1':float(o[0]), 'N':float(o[1]), '2':float(o[2])}
    return results

# --- 🚀 BOUTON DE LANCEMENT (ULTRA-RÉACTIF) ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("📊 SCANNER LES OPPORTUNITÉS"):
        # On sauvegarde les paramètres
        st.session_state['FB_TOTAL'] = MONTANT_FREEBET_TOTAL
        
        with st.spinner("Fusion des radars en cours..."):
            data = extract_all_data()
            wina_raw, betclic_raw = data['WINA'], data['BETCLIC']
            
            matchs_unifies = []
            clean_wina = {nettoyer_nom(k): (k, v) for k, v in wina_raw.items()}
            
            for b_name, b_odds in betclic_raw.items():
                b_clean = nettoyer_nom(b_name)
                if b_clean in clean_wina:
                    matchs_unifies.append({'t': b_name, 'sites': {'BETCLIC': b_odds, 'WINA': clean_wina[b_clean][1]}})
            
            st.toast(f"✅ {len(matchs_unifies)} matchs synchronisés !")
            st.session_state['matchs_unifies'] = matchs_unifies

# --- 🧐 ZONE D'AFFICHAGE INTELLIGENTE (Si scan effectué) ---
if 'matchs_unifies' in st.session_state and st.session_state['matchs_unifies']:
    matchs_unifies = st.session_state['matchs_unifies']
    MONTANT_FREEBET_TOTAL = st.session_state['FB_TOTAL']
    best_results = []
    issues_combinées = list(itertools.product(['1', 'N', '2'], repeat=2))

    # Calcul des rendements pour chaque duo (Limité à 1500 itérations pour la vitesse)
    for m1, m2 in itertools.combinations(matchs_unifies, 2):
        combos = []
        somme_probabilites_inverse_freebet = 0
        
        for i1, i2 in issues_combinées:
            best_cote_combinée, best_site = 0, ""
            
            for s in ['WINA', 'BETCLIC']:
                if s in m1['sites'] and s in m2['sites']:
                    c = m1['sites'][s][i1] * m2['sites'][s][i2]
                    if c > best_cote_combinée: best_cote_combinée, best_site = c, s
            
            if best_cote_combinée > 1.2:
                # La "probabilité perçue" en freebet est 1/(Cote - 1)
                somme_probabilites_inverse_freebet += 1 / (best_cote_combinée - 1)
                combos.append({'res': f"{i1}-{i2}", 'cote': best_cote_combinée, 'site': best_site})
        
        if len(combos) == 9:
            rendement_conversion = (1 / somme_probabilites_inverse_freebet) * 100
            best_results.append({'m1': m1['t'], 'm2': m2['t'], 'conv': rendement_conversion, 'combos': combos, 'sp': somme_probabilites_inverse_freebet})

    # Tri par meilleur rendement de conversion
    best_results.sort(key=lambda x: x['conv'], reverse=True)

    if best_results:
        st.divider()
        st.subheader("💎 Meilleures opportunités trouvées")
        
        # On affiche les 3 meilleures opportunités pour plus de choix
        for rank, top in enumerate(best_results[:3]):
            with st.expander(f"🏆 Pépites #{rank+1} - Conversion {top['conv']:.2f}% (Gain Net Garanti)", expanded=(rank == 0)):
                
                # --- NOUVEAU : GESTION DES PLAFONDS INTELLIGENTE ---
                pw_raw = sum(1/(c['cote']-1) for c in top['combos'] if c['site'] == 'WINA')
                pb_raw = sum(1/(c['cote']-1) for c in top['combos'] if c['site'] == 'BETCLIC')
                sp = pw_raw + pb_raw
                
                budget_libre_wina = (MAX_WINA * sp * (top['conv']/100)) if pw_raw > 0 else float('inf')
                budget_libre_bc = (MAX_BETCLIC * sp * (top['conv']/100)) if pb_raw > 0 else float('inf')
                
                budget_maximum_conseillé = min(MONTANT_FREEBET_TOTAL, budget_libre_wina, budget_libre_bc)
                gain_net_garanti = budget_maximum_conseillé * (top['conv']/100)
                
                # Header du duo
                m1_name = top['m1'].split(' - ')
                m2_name = top['m2'].split(' - ')
                
                c_m1, c_m2, c_m3 = st.columns([1, 0.3, 1])
                with c_m1: st.markdown(f"<p class='big-font' style='text-align:right;'>{m1_name[0]}<br>{m1_name[1]}</p>", unsafe_allow_html=True)
                with c_m2: st.markdown("<p style='text-align:center; font-size:30px;'>+</p>", unsafe_allow_html=True)
                with c_m3: st.markdown(f"<p class='big-font' style='text-align:left;'>{m2_name[0]}<br>{m2_name[1]}</p>", unsafe_allow_html=True)

                # NOUVEAU : Affichage des Métriques Clés
                c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
                c_kpi1.metric("Conversion", f"{top['conv']:.2f}%", help="Combien tu récupères de cash sur 100€ de freebet.")
                c_kpi2.metric("Gain Net Garanti", f"{gain_net_garanti:.2f} €", help="L'argent réel qui arrivera sur ton compte peu importe les résultats.")
                c_kpi3.metric("Budget Freebet Joué", f"{budget_maximum_conseillé:.2f} €", help=f"Basé sur ton entrée et tes plafonds de mise. (Reste {MONTANT_FREEBET_TOTAL - budget_maximum_conseillé:.2f}€ inutilisés si < total)")
                st.divider()

                # --- NOUVEAU : AFFICHAGE DES 9 TICKETS EN GRILLE 3x3 (Mobile Friendly) ---
                st.markdown("##### 📝 Tes 9 tickets à placer :")
                for r in range(3):
                    cols = st.columns(3)
                    for c in range(3):
                        index = r * 3 + c
                        ticket = top['combos'][index]
                        
                        # VRAIE FORMULE FREEBET : Mise = ( (1 / (Cote - 1)) / Somme(Probabilités)) * Budget
                        mise_equilibrée = ( (1 / (ticket['cote'] - 1)) / top['sp'] ) * budget_maximum_conseillé
                        
                        bookie_color = "#FF1E1E" if ticket['site'] == 'WINA' else "#FF1E1E" # Style Wina/Bc interchangeable
                        # Structure HTML custom pour mobile
                        cols[c].markdown(f"""
                        <div class='ticket-card'>
                            <p style='margin:0; text-align:center;'>ISSUE : <b>[{ticket['res']}]</b></p>
                            <p style='margin:0; text-align:center; color:{bookie_color};'>BANQUE : {ticket['site']}</p>
                            <p style='margin:10px 0; text-align:center;'>Cote: <b>{ticket['cote']:.2f}</b></p>
                            <p style='margin:0; text-align:center; background-color:#333; padding:5px; border-radius:5px;'>Mise : <b>{mise_equilibrée:.2f} €</b></p>
                        </div>
                        """, unsafe_allow_html=True)
                st.markdown("---")
                
                # Alerte Plafonds si budget réduit
                if budget_maximum_conseillé < MONTANT_FREEBET_TOTAL:
                    st.warning(f"⚠️ Budget réduit de {MONTANT_FREEBET_TOTAL - budget_maximum_conseillé:.2f}€ pour respecter tes plafonds stricts (Plaisir d'Adrien à Toulouse).")

    else:
        st.warning("Aucun duo compatible trouvé pour l'instant. Relance dans quelques minutes.")
else:
    st.info("👋 Bienvenue Adrien ! Appuie sur le bouton pour scanner l'Europe.")
