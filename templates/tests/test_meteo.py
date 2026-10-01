# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du module météo (outils_meteo.py).

Garanties :
- Aucun appel réseau sortant (utilisation de mocks httpx).
- Vérification de la conversion WMO.
- En cas d'erreur ou de timeout : un message d'erreur qui nomme la cause, jamais une prévision de remplacement.
"""

from unittest.mock import MagicMock

import httpx

from outils_meteo import description_wmo, obtenir_meteo


def test_description_wmo():
    """Vérifie la bonne traduction des codes météo WMO."""
    assert description_wmo(0) == "ciel dégagé et ensoleillé"
    assert description_wmo(3) == "ciel couvert"
    assert description_wmo(61) == "faible pluie"
    assert description_wmo(9999) == "conditions variables"


def test_obtenir_meteo_succes(monkeypatch):
    """Vérifie le flux nominal d'obtention de la météo avec géocodage et prévisions mockés."""
    reponse_geo = MagicMock()
    reponse_geo.raise_for_status = MagicMock()
    reponse_geo.json.return_value = {
        "results": [
            {
                "name": "Bordeaux",
                "latitude": 44.8378,
                "longitude": -0.5792,
                "country": "France",
            }
        ]
    }

    reponse_forecast = MagicMock()
    reponse_forecast.raise_for_status = MagicMock()
    reponse_forecast.json.return_value = {
        "daily": {
            "temperature_2m_max": [22.4],
            "temperature_2m_min": [12.1],
            "weather_code": [0],
        }
    }

    def mock_get(self, url, **kwargs):
        if "geocoding-api" in url:
            return reponse_geo
        return reponse_forecast

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    resultat = obtenir_meteo("Bordeaux")
    assert "Bordeaux" in resultat
    assert "de 12 à 22 °C" in resultat
    assert "ciel dégagé et ensoleillé" in resultat


def test_obtenir_meteo_ville_introuvable(monkeypatch):
    """Vérifie le message d'erreur lorsque le géocodage ne renvoie aucun résultat."""
    reponse_geo = MagicMock()
    reponse_geo.raise_for_status = MagicMock()
    reponse_geo.json.return_value = {"results": []}

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kwargs: reponse_geo)

    resultat = obtenir_meteo("VilleInconnue12345")
    assert resultat.startswith("Erreur : météo non récupérée pour VilleInconnue12345 (ville introuvable).")


def test_obtenir_meteo_timeout(monkeypatch):
    """Vérifie le message d'erreur en cas de timeout réseau."""
    def mock_timeout(self, url, **kwargs):
        raise httpx.TimeoutException("Délai dépassé")

    monkeypatch.setattr(httpx.Client, "get", mock_timeout)

    resultat = obtenir_meteo("Toulouse")
    assert "Open-Meteo n'a pas répondu en 5 secondes" in resultat
    assert resultat.startswith("Erreur : météo non récupérée")


def test_obtenir_meteo_erreur_http(monkeypatch):
    """Vérifie le message d'erreur en cas d'erreur HTTP ou réseau."""
    def mock_http_error(self, url, **kwargs):
        req = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("Erreur 500", request=req, response=httpx.Response(500, request=req))

    monkeypatch.setattr(httpx.Client, "get", mock_http_error)

    resultat = obtenir_meteo("Strasbourg")
    assert "l'API Open-Meteo n'a pas répondu" in resultat
    assert resultat.startswith("Erreur : météo non récupérée")



def test_obtenir_meteo_lit_ses_adresses_dans_la_config(monkeypatch):
    """Vérifie que les adresses d'Open-Meteo viennent de la config : un CHECK de panne ne touche pas au code."""
    import outils_meteo

    monkeypatch.setattr(outils_meteo, "URL_METEO_GEOCODAGE", "https://adresse-fausse.test/geocodage")
    adresses_appelees = []

    def mock_get(self, url, **kwargs):
        adresses_appelees.append(url)
        raise httpx.ConnectError("Adresse injoignable")

    monkeypatch.setattr(httpx.Client, "get", mock_get)

    resultat = obtenir_meteo("Lyon")

    assert adresses_appelees == ["https://adresse-fausse.test/geocodage"]
    assert resultat.startswith("Erreur : météo non récupérée")
