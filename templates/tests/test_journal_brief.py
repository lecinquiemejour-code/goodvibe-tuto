# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests de l'encadrement de la recette du brief dans le journal (Features 6 et 14).

Tous les déclencheurs (bouton, cron, webhook) laissent la même trace, écrite par
brief.py et jamais par l'appelant :
- une ligne `brief` d'ouverture qui cite le déclencheur ;
- une ligne `<déclencheur>:brief` de fermeture, avec la durée totale, qui dit
  « brief terminé », « brief déjà produit », l'échec et sa cause, ou « interrompue ».
Aucun appel réseau : la boucle d'agent et l'illustration sont simulées.
"""

import pytest

import brief
import journal
from brief import generer_brief, generer_brief_complet_stream
from fragments import RELEVE, REPONSE, Fragment

STATS_SANS_IMAGE = {"tokens_entree": 0, "tokens_sortie": 0, "nb_images": 0, "duree_ms": 0}


@pytest.fixture
def recette_simulee(monkeypatch):
    """Simule la rédaction (un texte, un relevé) et une illustration en échec propre."""

    def faux_repondre(*args, **kwargs):
        yield Fragment(nature=REPONSE, texte="Bonjour, voici votre brief du jour.")
        yield Fragment(
            nature=RELEVE,
            texte="Tokens : 100 entrée, 0 réflexion, 50 sortie — Tours : 1",
            chiffres={"tokens_entree": 100, "tokens_reflexion": 0, "tokens_sortie": 50, "duree_ms": 500},
        )

    def fausse_illustration(**kwargs):
        return None, "Erreur : illustration non générée", "", dict(STATS_SANS_IMAGE)

    monkeypatch.setattr(brief, "repondre", faux_repondre)
    monkeypatch.setattr(brief, "generer_illustration", fausse_illustration)


def lignes_du_journal(etape: str):
    """Les lignes du journal pour une étape donnée, de la plus ancienne à la plus récente."""
    return [e for e in reversed(journal.get_dernieres_activites(limite=30)) if e["etape"] == etape]


def test_encadrement_brief_termine(recette_simulee):
    """Une recette qui va au bout : ouverture `brief` citant le déclencheur, fermeture `cron:brief`."""
    generer_brief(forcer=True, declencheur="cron")

    ouvertures = lignes_du_journal("brief")
    assert any("déclencheur : cron" in ligne["detail"] for ligne in ouvertures)

    fermetures = lignes_du_journal("cron:brief")
    assert len(fermetures) == 1
    assert fermetures[0]["detail"] == "brief terminé"
    assert fermetures[0]["duree_ms"] is not None


def test_encadrement_brief_deja_produit(recette_simulee):
    """Le second lancement du cron sans forcer se ferme aussi, en disant « déjà produit »."""
    generer_brief(forcer=True, declencheur="cron")
    generer_brief(forcer=False, declencheur="cron")

    fermetures = lignes_du_journal("cron:brief")
    assert [f["detail"] for f in fermetures] == ["brief terminé", "brief déjà produit"]


def test_encadrement_meme_forme_pour_chaque_declencheur(recette_simulee):
    """Bouton, cron et webhook laissent la même trace, seul le nom change."""
    for nom in ("bouton", "cron", "webhook"):
        generer_brief(forcer=True, declencheur=nom)
        fermetures = lignes_du_journal(f"{nom}:brief")
        assert len(fermetures) == 1
        assert fermetures[0]["detail"] == "brief terminé"


def test_encadrement_echec_note_puis_remonte(monkeypatch):
    """Une recette qui plante : la fermeture dit l'échec et sa cause, puis l'erreur remonte."""

    def repondre_en_panne(*args, **kwargs):
        raise RuntimeError("modèle indisponible")
        yield  # jamais atteint : fait de cette fonction un générateur, comme la vraie

    monkeypatch.setattr(brief, "repondre", repondre_en_panne)

    with pytest.raises(RuntimeError):
        generer_brief(forcer=True, declencheur="webhook")

    fermetures = lignes_du_journal("webhook:brief")
    assert len(fermetures) == 1
    assert "échec" in fermetures[0]["detail"]
    assert "modèle indisponible" in fermetures[0]["detail"]


def test_encadrement_interruption_par_l_appelant(recette_simulee):
    """La page rechargée en pleine rédaction : le journal dit « interrompue », rien n'est enregistré."""
    etapes = generer_brief_complet_stream(forcer=True, declencheur="bouton")
    next(etapes)  # la première étape affichée : « préparation en cours »
    etapes.close()  # l'appelant cesse de lire, comme Gradio quand le navigateur part

    fermetures = lignes_du_journal("bouton:brief")
    assert len(fermetures) == 1
    assert "interrompue" in fermetures[0]["detail"]
