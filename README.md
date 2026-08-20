# Conversion Freebets

Application Streamlit pour optimiser la conversion de freebets sur **Winamax, Betclic et Unibet**.

## Fonctionnement
- récupération des cotes 1N2 via The Odds API ;
- comparaison des trois bookmakers français ;
- construction de combinaisons de 2 matchs ;
- couverture des 9 issues possibles ;
- répartition automatique des mises selon les soldes freebets ;
- classement des meilleures conversions ;
- cache 5 minutes pour limiter la consommation du quota API.

## Lancement Streamlit
Le point d'entrée recommandé est `app.py`.

```bash
pip install -r requirements.txt
streamlit run app.py
```

`optimv5.py` reste présent comme point d'entrée de compatibilité pour un ancien déploiement Streamlit.

## Secrets
Ne jamais écrire une clé API ou un token Telegram directement dans le dépôt.

Dans Streamlit Community Cloud, ajouter dans **Settings > Secrets** :

```toml
THE_ODDS_API_KEY = "..."
```

En local, copier `.streamlit/secrets.toml.example` vers `.streamlit/secrets.toml` puis renseigner la clé.

## Sécurité
Un ancien token Telegram a été publié dans l'historique Git du dépôt. Il doit être révoqué/régénéré avant toute réactivation des notifications Telegram.
