# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du client MCP (mcp_client.py) et de sa panne vue par l'agent.

Garanties :
- Le serveur MCP n'est jamais lancé : ses fonctions asynchrones sont simulées.
- Un serveur qui ne démarre pas lève une erreur et laisse une ligne au journal :
  l'outil ne disparaît pas du catalogue sans que personne ne le sache (Fiche 8).
- Le client dit où la chaîne a cassé (le serveur, ou l'outil), sans parler d'horoscope.
"""

import pytest

import mcp_client
import outils
from agent import repondre
from fragments import COULISSES
from horoscope import ERREUR_SERVEUR_FETCH
from journal import get_dernieres_activites
from mcp_client import (
    ISSUE_OK,
    ISSUE_OUTIL,
    ISSUE_SERVEUR,
    OutilMCPEnEchec,
    ServeurMCPNonDemarre,
    appeler_outil_mcp,
    lister_outils_mcp,
)
from tests.conftest import fabriquer_flux_texte


def simuler_issue(monkeypatch, issue: str, texte: str) -> None:
    """Fait rendre à l'appel d'outil asynchrone une issue choisie, sans lancer le serveur."""

    async def faux_appel(nom, arguments):
        return issue, texte

    monkeypatch.setattr(mcp_client, "_async_appeler_outil", faux_appel)


def test_lister_outils_serveur_non_demarre(monkeypatch):
    """Vérifie que list_tools en échec lève une erreur et laisse une ligne au journal."""

    async def serveur_introuvable():
        raise FileNotFoundError("commande-qui-n-existe-pas")

    monkeypatch.setattr(mcp_client, "_async_lister_outils", serveur_introuvable)

    with pytest.raises(ServeurMCPNonDemarre):
        lister_outils_mcp()

    lignes = [a for a in get_dernieres_activites() if a["etape"] == "mcp:list_tools"]
    assert len(lignes) == 1
    assert "le serveur MCP n'a pas démarré" in lignes[0]["detail"]


def test_appeler_outil_rend_le_texte(monkeypatch):
    """Vérifie l'appel normal : le texte lu est rendu, et le journal note l'appel sans le texte."""
    simuler_issue(monkeypatch, ISSUE_OK, "Texte lu par fetch")

    assert appeler_outil_mcp("fetch", {"url": "https://exemple.test"}) == "Texte lu par fetch"

    lignes = [a for a in get_dernieres_activites() if a["etape"] == "mcp:fetch"]
    assert len(lignes) == 1
    assert "Texte lu par fetch" not in lignes[0]["detail"]
    assert "exemple.test" not in lignes[0]["detail"]


def test_appeler_outil_serveur_non_demarre(monkeypatch):
    """Vérifie que le serveur non démarré lève l'erreur qui le dit."""
    simuler_issue(monkeypatch, ISSUE_SERVEUR, "FileNotFoundError : uvx")

    with pytest.raises(ServeurMCPNonDemarre):
        appeler_outil_mcp("fetch", {"url": "https://exemple.test"})

    lignes = [a for a in get_dernieres_activites() if a["etape"] == "mcp:fetch"]
    assert "le serveur MCP n'a pas démarré" in lignes[0]["detail"]


def test_appeler_outil_en_echec(monkeypatch):
    """Vérifie qu'une erreur rendue par l'outil lève l'erreur qui le dit."""
    simuler_issue(monkeypatch, ISSUE_OUTIL, "Failed to fetch: 500")

    with pytest.raises(OutilMCPEnEchec):
        appeler_outil_mcp("fetch", {"url": "https://exemple.test"})

    lignes = [a for a in get_dernieres_activites() if a["etape"] == "mcp:fetch"]
    assert "a rendu une erreur" in lignes[0]["detail"]


def test_catalogue_signale_le_serveur_non_demarre(monkeypatch):
    """Vérifie que le catalogue rend l'erreur quand le serveur MCP n'annonce pas ses outils."""

    def serveur_non_demarre():
        raise ServeurMCPNonDemarre("uvx introuvable")

    monkeypatch.setattr(outils, "lister_outils_mcp", serveur_non_demarre)

    specs, erreurs = outils.obtenir_specifications_outils()

    assert "fetch" not in [s["name"] for s in specs]
    assert erreurs == [ERREUR_SERVEUR_FETCH]


def test_catalogue_contient_l_outil_annonce_par_le_serveur():
    """Vérifie que l'outil du serveur rejoint les fonctions locales, sans erreur."""
    specs, erreurs = outils.obtenir_specifications_outils()

    noms = [s["name"] for s in specs]
    assert "fetch" in noms
    assert "meteo" in noms
    assert erreurs == []


def test_agent_recoit_l_erreur_du_serveur_non_demarre(faux_gemini, monkeypatch):
    """Vérifie que l'erreur arrive au modèle et dans les coulisses, au lieu d'un outil disparu."""

    def serveur_non_demarre():
        raise ServeurMCPNonDemarre("uvx introuvable")

    monkeypatch.setattr(outils, "lister_outils_mcp", serveur_non_demarre)
    faux_gemini.interactions.scenarios = [fabriquer_flux_texte("Brief sans horoscope.")]

    fragments = list(repondre("Prépare mon brief", voir_reflexion=True))

    # Le modèle reçoit le message d'erreur dans son prompt système...
    prompt_envoye = faux_gemini.interactions.appels[0]["system_instruction"]
    assert ERREUR_SERVEUR_FETCH in prompt_envoye
    # ... sans l'outil fetch dans son catalogue
    assert "fetch" not in [o["name"] for o in faux_gemini.interactions.appels[0]["tools"]]
    # Les coulisses montrent l'erreur
    assert any(
        f.nature == COULISSES and ERREUR_SERVEUR_FETCH in f.texte for f in fragments
    )


def test_lister_outils_retient_la_liste(monkeypatch):
    """Vérifie que le serveur n'est interrogé qu'une fois : la liste est retenue ensuite."""
    appels = []

    async def faux_serveur():
        appels.append(1)
        return [{"type": "function", "name": "fetch", "description": "d", "parameters": {}}]

    monkeypatch.setattr(mcp_client, "_async_lister_outils", faux_serveur)

    premiere = lister_outils_mcp()
    seconde = lister_outils_mcp()

    assert len(appels) == 1
    assert [o["name"] for o in premiere] == ["fetch"]
    assert seconde == premiere
    # Modifier la liste reçue ne change pas la liste retenue
    seconde[0]["name"] = "autre"
    assert lister_outils_mcp()[0]["name"] == "fetch"


def test_lister_outils_ne_retient_pas_un_echec(monkeypatch):
    """Vérifie qu'un échec n'est pas retenu : la question est reposée à l'appel suivant."""
    appels = []

    async def serveur_capricieux():
        appels.append(1)
        if len(appels) == 1:
            raise FileNotFoundError("uvx introuvable")
        return [{"type": "function", "name": "fetch", "description": "d", "parameters": {}}]

    monkeypatch.setattr(mcp_client, "_async_lister_outils", serveur_capricieux)

    with pytest.raises(ServeurMCPNonDemarre):
        lister_outils_mcp()

    assert [o["name"] for o in lister_outils_mcp()] == ["fetch"]
    assert len(appels) == 2
