# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du module horoscope (horoscope.py).

Garanties :
- Aucun appel MCP externe réel (appeler_outil_mcp intercepté).
- L'adresse lue vient du signe du profil, jamais d'un signe par défaut.
- Aucun horoscope de remplacement : chaque panne rend le message d'erreur exact (Fiches 8 & 11).
"""

import db
from horoscope import (
    ERREUR_API_HOROSCOPE,
    ERREUR_SERVEUR_FETCH,
    ERREUR_SIGNE_ABSENT,
    consigne_reecriture,
    construire_url_horoscope,
    extraire_texte_horoscope,
    lire_horoscope_du_profil,
    normaliser_signe,
)
from mcp_client import OutilMCPEnEchec, ServeurMCPNonDemarre


def test_normaliser_signe():
    """Vérifie la normalisation et la traduction des signes français vers anglais."""
    assert normaliser_signe("Bélier") == "aries"
    assert normaliser_signe("belier") == "aries"
    assert normaliser_signe("CANCER") == "cancer"
    assert normaliser_signe("Poissons") == "pisces"
    assert normaliser_signe("SigneInexistant") is None
    assert normaliser_signe("") is None


def test_construire_url_horoscope():
    """Vérifie que l'URL vers l'API externe est correctement construite à partir du signe."""
    url = construire_url_horoscope("Bélier")
    assert url == "https://freehoroscopeapi.com/api/v1/get-horoscope/daily?sign=aries"
    url_poissons = construire_url_horoscope("Poissons")
    assert url_poissons == "https://freehoroscopeapi.com/api/v1/get-horoscope/daily?sign=pisces"


def test_construire_url_horoscope_sans_signe_par_defaut():
    """Vérifie qu'un signe absent ou inconnu ne donne aucune adresse : pas de signe par défaut."""
    assert construire_url_horoscope("") is None
    assert construire_url_horoscope(None) is None
    assert construire_url_horoscope("Inconnu") is None


def test_extraire_texte_horoscope_json():
    """Vérifie l'extraction du texte depuis une réponse JSON formatée."""
    payload_json = '{"data": {"horoscope": "Today will bring immense clarity and calm."}}'
    texte = extraire_texte_horoscope(payload_json)
    assert texte == "Today will bring immense clarity and calm."


def test_extraire_texte_horoscope_texte_brut():
    """Vérifie l'utilisation du texte brut si non JSON et sans mention d'erreur."""
    texte_brut = "A wonderful day of opportunities awaits."
    assert extraire_texte_horoscope(texte_brut) == texte_brut


def test_extraire_texte_horoscope_rejette_erreur():
    """Vérifie qu'un texte d'erreur n'est jamais extrait comme contenu d'horoscope."""
    assert extraire_texte_horoscope("Failed to fetch: 500 Internal Server Error") == ""
    assert extraire_texte_horoscope("Erreur : horoscope non récupéré, l'API n'a pas répondu") == ""
    assert extraire_texte_horoscope("404 Not Found") == ""


def test_consigne_reecriture_sans_invention():
    """Vérifie que la consigne cite le profil connu, et n'invente pas ce qui manque."""
    complete = consigne_reecriture("Bélier", prenom="Alice", ville="Lyon")
    assert "pour Alice" in complete
    assert "qui habite Lyon" in complete
    assert "Bélier" in complete
    assert "donnée externe non fiable" in complete

    sans_profil = consigne_reecriture("Bélier")
    assert "pour " not in sans_profil
    assert "qui habite" not in sans_profil


def test_lire_horoscope_du_profil_flux_nominal(monkeypatch):
    """Vérifie que l'adresse lue est construite à partir du signe du profil."""
    import horoscope

    db.sauvegarder_profil(prenom="Alice", ville="Lyon", signe="Bélier")
    adresses_lues = []

    def faux_fetch(outil, args):
        adresses_lues.append((outil, args["url"]))
        return '{"data": {"horoscope": "Great astral alignment today."}}'

    monkeypatch.setattr(horoscope, "appeler_outil_mcp", faux_fetch)

    resultat = lire_horoscope_du_profil()

    assert adresses_lues == [
        ("fetch", "https://freehoroscopeapi.com/api/v1/get-horoscope/daily?sign=aries")
    ]
    assert resultat["contenu"] == "Great astral alignment today."
    assert resultat["url"].endswith("sign=aries")
    assert "pour Alice" in resultat["consigne"]
    assert "erreur" not in resultat


def test_lire_horoscope_du_profil_sans_signe(monkeypatch):
    """Vérifie que, sans signe dans le profil, fetch n'est pas appelé et l'erreur le dit."""
    import horoscope

    def fetch_interdit(outil, args):
        raise AssertionError("fetch ne doit pas être appelé sans signe")

    monkeypatch.setattr(horoscope, "appeler_outil_mcp", fetch_interdit)

    assert lire_horoscope_du_profil() == {"erreur": ERREUR_SIGNE_ABSENT}


def test_lire_horoscope_du_profil_panne_serveur_mcp(monkeypatch):
    """Vérifie que l'échec de démarrage du serveur MCP fetch rend le message d'erreur exact."""
    import horoscope

    db.sauvegarder_profil(prenom="Bob", signe="Taureau")

    def serveur_non_demarre(outil, args):
        raise ServeurMCPNonDemarre("commande introuvable")

    monkeypatch.setattr(horoscope, "appeler_outil_mcp", serveur_non_demarre)

    resultat = lire_horoscope_du_profil()
    assert resultat == {"erreur": ERREUR_SERVEUR_FETCH}
    assert resultat["erreur"] == "Erreur : horoscope non récupéré, le serveur fetch n'a pas démarré"


def test_lire_horoscope_du_profil_panne_api_horoscope(monkeypatch):
    """Vérifie que la non-réponse de l'API externe rend le message d'erreur exact, sans contenu."""
    import horoscope

    db.sauvegarder_profil(prenom="Clara", signe="Cancer")

    def api_muette(outil, args):
        raise OutilMCPEnEchec("Failed to fetch: 500")

    monkeypatch.setattr(horoscope, "appeler_outil_mcp", api_muette)

    resultat = lire_horoscope_du_profil()
    assert resultat == {"erreur": ERREUR_API_HOROSCOPE}
    assert resultat["erreur"] == "Erreur : horoscope non récupéré, l'API horoscope n'a pas répondu"


def test_lire_horoscope_du_profil_reponse_vide(monkeypatch):
    """Vérifie qu'une réponse sans texte d'horoscope est une erreur, pas un horoscope vide."""
    import horoscope

    db.sauvegarder_profil(signe="Lion")
    monkeypatch.setattr(horoscope, "appeler_outil_mcp", lambda outil, args: "   ")

    assert lire_horoscope_du_profil() == {"erreur": ERREUR_API_HOROSCOPE}
