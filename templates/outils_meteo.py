# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Module d'intégration météo pour GoodVibe (Feature 7).

Interroge l'API Open-Meteo (sans clé, sans inscription) pour obtenir le géocodage
et les prévisions réelles du jour, avec un timeout strict de 5 secondes,
conversion en phrase concise, et message d'erreur qui nomme la cause si le service ne répond pas.
"""

import logging
import time
from typing import Dict

import httpx

from config import URL_METEO_GEOCODAGE, URL_METEO_PREVISION
from journal import consigner_activite

logger = logging.getLogger("goodvibe.meteo")

TIMEOUT_SECONDS = 5.0

# Table de correspondance des codes météo WMO en français
WMO_CODES: Dict[int, str] = {
    0: "ciel dégagé et ensoleillé",
    1: "plutôt dégagé",
    2: "partiellement nuageux",
    3: "ciel couvert",
    45: "brouillard",
    48: "brouillard givrant",
    51: "légère bruine",
    53: "bruine modérée",
    55: "bruine dense",
    56: "légère bruine verglaçante",
    57: "bruine verglaçante dense",
    61: "faible pluie",
    63: "pluie modérée",
    65: "forte pluie",
    66: "faible pluie verglaçante",
    67: "forte pluie verglaçante",
    71: "faibles chutes de neige",
    73: "chutes de neige modérées",
    75: "fortes chutes de neige",
    77: "grains de neige",
    80: "faibles averses",
    81: "averses modérées",
    82: "violentes averses",
    85: "légères averses de neige",
    86: "fortes averses de neige",
    95: "orages",
    96: "orage avec faible grêle",
    99: "orage avec forte grêle",
}


def description_wmo(code: int) -> str:
    """Traduit un code météo numérique WMO en description courante en français."""
    return WMO_CODES.get(code, "conditions variables")


def obtenir_meteo(ville: str) -> str:
    """Interroge Open-Meteo pour obtenir les prévisions du jour pour une commune.

    Effectue deux requêtes HTTP séquentielles :
    1. Géocodage de la ville (recherche lat/lon).
    2. Prévisions du jour à ces coordonnées.

    Garantit un message d'erreur clair sans lever d'exception en cas de défaillance.

    Args:
        ville: Le nom de la commune demandée.

    Returns:
        Une phrase concise résumant les températures et le ciel, ou un message d'erreur.
    """
    nom_propre = ville.strip() if ville else ""
    if not nom_propre:
        return "Erreur : météo non récupérée, aucun nom de ville fourni."

    t0 = time.time()

    try:
        # Étape 1 : Géocodage de la ville avec timeout strict (adresse lue dans la config)
        url_geocoding = URL_METEO_GEOCODAGE
        params_geo = {
            "name": nom_propre,
            "count": 1,
            "language": "fr",
            "format": "json",
        }

        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp_geo = client.get(url_geocoding, params=params_geo)
            resp_geo.raise_for_status()
            data_geo = resp_geo.json()

            resultats = data_geo.get("results")
            if not resultats or len(resultats) == 0:
                consigner_activite("outil:meteo", "Ville inconnue au géocodage")
                return f"Erreur : météo non récupérée pour {nom_propre} (ville introuvable)."

            # Règle tuto : prendre le premier résultat et journaliser le pays
            premier = resultats[0]
            latitude = premier.get("latitude")
            longitude = premier.get("longitude")
            nom_trouve = premier.get("name", nom_propre)
            pays = premier.get("country", "")

            # Étape 2 : Récupération des prévisions du jour (adresse lue dans la config)
            url_forecast = URL_METEO_PREVISION
            params_forecast = {
                "latitude": latitude,
                "longitude": longitude,
                "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
                "timezone": "auto",
            }

            resp_forecast = client.get(url_forecast, params=params_forecast)
            resp_forecast.raise_for_status()
            data_forecast = resp_forecast.json()

            daily = data_forecast.get("daily", {})
            t_max_list = daily.get("temperature_2m_max", [])
            t_min_list = daily.get("temperature_2m_min", [])
            w_code_list = daily.get("weather_code", [])

            if not t_max_list or not t_min_list or not w_code_list:
                consigner_activite("outil:meteo", "Données prévisions manquantes")
                return f"Erreur : météo non récupérée pour {nom_trouve} (données de prévision indisponibles)."

            t_max = round(float(t_max_list[0]))
            t_min = round(float(t_min_list[0]))
            code_meteo = int(w_code_list[0])
            ciel = description_wmo(code_meteo)

            duree_ms = int((time.time() - t0) * 1000)
            consigner_activite(
                "outil:meteo",
                f"Météo obtenue ({pays})",
                duree_ms=duree_ms,
            )

            # Règle tuto : retourner une phrase claire, pas de JSON brut
            return f"{nom_trouve} : de {t_min} à {t_max} °C, {ciel}."

    except httpx.TimeoutException:
        logger.warning("Timeout dépassé lors de la requête météo pour %s", nom_propre)
        consigner_activite("outil:meteo", "Timeout Open-Meteo")
        return f"Erreur : météo non récupérée, Open-Meteo n'a pas répondu en {int(TIMEOUT_SECONDS)} secondes."

    except httpx.HTTPError as e:
        logger.warning("Erreur HTTP lors de la requête météo pour %s : %s", nom_propre, e)
        consigner_activite("outil:meteo", f"Erreur HTTP Open-Meteo ({type(e).__name__})")
        return f"Erreur : météo non récupérée pour {nom_propre}, l'API Open-Meteo n'a pas répondu ({type(e).__name__})."

    except Exception as e:
        logger.exception("Erreur inattendue lors de la requête météo : %s", e)
        consigner_activite("outil:meteo", f"Erreur inattendue météo ({type(e).__name__})")
        return f"Erreur : météo non récupérée pour {nom_propre} ({type(e).__name__})."
