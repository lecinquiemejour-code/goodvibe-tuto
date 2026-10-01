# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Configuration centrale de GoodVibe.

Toutes les variables d'environnement et constantes sont lues ici :
une seule source de vérité pour tout le projet.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Chargement du fichier .env local
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Clé API Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Modèle texte retenu : aucun nom écrit dans le code, car les modèles changent vite.
# L'agent le recommande au PLAN de la fiche 1, d'après la documentation officielle Google du jour.
MODELE_TEXTE = os.getenv("MODELE_TEXTE", "").strip()

# Modèle image retenu : même principe, recommandé au PLAN de la fiche 10.
MODELE_IMAGE = os.getenv("MODELE_IMAGE", "").strip()

# Dossier local de stockage des illustrations générées
DOSSIER_IMAGES = BASE_DIR / "data" / "images"

# Garde-fou : nombre maximal de tours par exécution
MAX_TOURS = int(os.getenv("MAX_TOURS", "5"))

# Réglages du modèle (validés d'après la doc Google)
# La limite de longueur couvre la réflexion du modèle ET le texte qu'il écrit : trop basse,
# la réflexion la consomme et la réponse est coupée (agent.py le signale). À 1000, deux
# briefs sur cinq étaient coupés avec une réflexion « medium » ; 4000 laisse de la marge
# et reste un garde-fou de dépense. C'est un plafond : seuls les tokens produits se paient.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "4000"))
THINKING_LEVEL = os.getenv("THINKING_LEVEL", "medium")

# Paramètres de l'interface web Gradio. Aucune valeur par défaut : un oubli dans le .env
# ne doit jamais ouvrir la page avec un mot de passe connu de tous (voir verifier_acces_web).
WEB_USER = os.getenv("WEB_USER", "").strip()
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "").strip()
PORT_GRADIO = int(os.getenv("PORT_GRADIO", "7860"))

# Paramètres du webhook des pense-bêtes (Feature 14)
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
PORT_WEBHOOK = int(os.getenv("PORT_WEBHOOK", "8000"))

# Configuration du serveur MCP fetch (Feature 8)
# Sur le VPS, ni le service ni le cron ne connaissent le dossier où uvx est installé :
# le .env du serveur donne son chemin complet (deploy/deployer.sh l'y inscrit).
MCP_FETCH_COMMAND = os.getenv("MCP_FETCH_COMMAND", "uvx")
MCP_FETCH_ARGS = ["mcp-server-fetch"]

# Adresse de l'API horoscope, sans le signe : horoscope.py la complète à partir du profil
URL_API_HOROSCOPE = os.getenv(
    "URL_API_HOROSCOPE",
    "https://freehoroscopeapi.com/api/v1/get-horoscope/daily",
)

# Adresses de l'API météo Open-Meteo (Feature 7) : le géocodage trouve la ville, la prévision
# donne le temps du jour. Elles se changent dans le .env pour un CHECK de panne, sans toucher au code.
URL_METEO_GEOCODAGE = os.getenv(
    "URL_METEO_GEOCODAGE",
    "https://geocoding-api.open-meteo.com/v1/search",
)
URL_METEO_PREVISION = os.getenv(
    "URL_METEO_PREVISION",
    "https://api.open-meteo.com/v1/forecast",
)

# Chemin vers la fiche de poste de GoodVibe
PROMPT_SYSTEME_PATH = BASE_DIR / "prompt_systeme.md"

# Chemin vers la consigne du directeur artistique : le texte envoyé au modèle texte pour
# qu'il compose le prompt visuel de l'image du jour (Feature 10). Comme le prompt système,
# il se lit et s'ajuste sans toucher au code.
PROMPT_IMAGE_PATH = BASE_DIR / "prompt_image.md"


def lire_prompt_systeme() -> str:
    """Lit et renvoie le prompt système depuis son fichier Markdown.

    Returns:
        Le texte de la fiche de poste de GoodVibe.

    Raises:
        FileNotFoundError: si le fichier est absent. Aucune fiche de poste de secours n'existe
            dans le code : sans ses règles, GoodVibe ne doit pas répondre.
    """
    if not PROMPT_SYSTEME_PATH.exists():
        raise FileNotFoundError(f"le fichier {PROMPT_SYSTEME_PATH.name} est introuvable")
    return PROMPT_SYSTEME_PATH.read_text(encoding="utf-8").strip()


def verifier_config() -> None:
    """Vérifie que la configuration minimale est présente."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "La clé API Google Gemini est manquante !\n"
            "Veuillez renseigner votre GEMINI_API_KEY dans le fichier .env "
            "(clé à créer sur https://aistudio.google.com/apikey, facturation activée sur son projet : fiche 1)."
        )
    if not MODELE_TEXTE:
        raise ValueError(
            "MODELE_TEXTE manquant dans le fichier .env : "
            "l'agent vous le recommande au PLAN de la fiche 1."
        )
    if not MODELE_IMAGE:
        raise ValueError(
            "MODELE_IMAGE manquant dans le fichier .env : "
            "l'agent vous le recommande au PLAN de la fiche 10."
        )


def verifier_acces_web() -> None:
    """Vérifie que l'identifiant et le mot de passe de la page web sont renseignés.

    Appelée par la seule page web : le chat terminal et le cron n'en ont pas besoin.

    Raises:
        ValueError: si WEB_USER ou WEB_PASSWORD est vide dans le .env.
    """
    if not WEB_USER or not WEB_PASSWORD:
        raise ValueError(
            "WEB_USER ou WEB_PASSWORD manquant dans le fichier .env : la page web "
            "ne s'ouvre pas sans eux. Choisissez un mot de passe long, jamais celui d'un autre compte."
        )
