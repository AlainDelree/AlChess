"""
nicsoft/utils/net_safety.py — NicLink
Vérification du schéma d'une adresse distante avant son ouverture par
urllib, pour les quelques adresses constantes du code (jamais saisies par
l'utilisateur) téléchargées sans passer par le serveur web : Wikipedia
(download_eco_wiki.py), API Claude/OpenAI (llm_provider.py), service
edge-tts (tts_engine.py) — issue #288, famille B de l'audit sécurité
(bandit B310 / ruff S310).

N'importe jamais la couche web (nicsoft.web) : utilisé aussi en CLI pur
(download_eco_wiki.py exécuté hors serveur).
"""


def ensure_https(url: str) -> None:
    """Lève ValueError si `url` ne commence pas par https:// — à appeler
    avant toute ouverture d'une adresse distante avec urllib.request.urlopen."""
    if not url.startswith("https://"):
        raise ValueError(f"Adresse refusée (https:// requis pour une adresse distante) : {url}")
