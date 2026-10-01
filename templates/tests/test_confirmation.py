# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests de la confirmation des suppressions par l'utilisateur (confirmation.py, Features 5 et 14).

Garanties :
- Un appel direct à un outil de suppression ne supprime rien : il dépose une demande.
- Seul le geste de l'utilisateur (confirmer) supprime, et uniquement l'élément affiché.
- Une nouvelle proposition remplace l'ancienne ; un refus, ou une seconde confirmation,
  ne supprime rien.
- La même règle vaut dans la boucle d'agent, dans la page web et au terminal.
- Le journal ne cite jamais le texte d'une note ni d'un pense-bête.
"""

import chat_terminal
import confirmation
import db
import journal
import outils
from agent import repondre
from interface import annuler_suppression, confirmer_suppression
from tests.conftest import fabriquer_flux_outil


def lignes_confirmation():
    """Les lignes du journal écrites par la confirmation, de la plus ancienne à la plus récente."""
    return [e for e in reversed(journal.get_dernieres_activites(limite=30)) if e["etape"] == "confirmation"]


def test_appel_direct_de_l_outil_ne_supprime_rien():
    """L'outil appelé tel quel, comme le ferait le modèle, ne supprime pas : il propose."""
    id_note = db.ajouter_note("Dentiste mardi à 10 h")

    resultat = outils.executer_outil("supprimer_note", {"id_note": id_note})

    assert resultat["statut"] == "confirmation_requise"
    assert len(db.get_notes()) == 1
    demande = confirmation.en_attente()
    assert demande is not None
    assert demande.type == confirmation.NOTE
    assert demande.id == id_note
    # L'utilisateur voit le numéro et le texte de ce qui sera supprimé
    assert f"n° {id_note}" in demande.libelle
    assert "Dentiste mardi à 10 h" in demande.libelle
    assert confirmation.question(demande).startswith("Supprimer la note")


def test_confirmer_ne_supprime_que_l_element_affiche():
    """La confirmation agit sur la note désignée par la demande, et sur elle seule."""
    id1 = db.ajouter_note("Première note")
    id2 = db.ajouter_note("Deuxième note")
    outils.supprimer_note(id1)

    message = confirmation.confirmer()

    assert message == f"Note n° {id1} retirée."
    assert [n["id"] for n in db.get_notes()] == [id2]
    assert confirmation.en_attente() is None


def test_nouvelle_proposition_remplace_l_ancienne():
    """Une confirmation ne vaut que pour la dernière demande affichée."""
    id1 = db.ajouter_note("Première note")
    id2 = db.ajouter_note("Deuxième note")
    outils.supprimer_note(id1)
    outils.supprimer_note(id2)

    confirmation.confirmer()

    assert [n["id"] for n in db.get_notes()] == [id1]


def test_refuser_ne_supprime_rien():
    """Un refus abandonne la demande : rien n'est supprimé, plus rien n'attend."""
    id_note = db.ajouter_note("Acheter du pain")
    outils.supprimer_note(id_note)

    message = confirmation.refuser()

    assert message == confirmation.RIEN_SUPPRIME
    assert len(db.get_notes()) == 1
    assert confirmation.en_attente() is None


def test_seconde_confirmation_sans_effet():
    """Après une confirmation, il ne reste rien à confirmer : un second geste ne supprime rien."""
    id1 = db.ajouter_note("Première note")
    db.ajouter_note("Deuxième note")
    outils.supprimer_note(id1)
    confirmation.confirmer()

    assert confirmation.confirmer() == confirmation.RIEN_EN_ATTENTE
    assert confirmation.refuser() == confirmation.RIEN_EN_ATTENTE
    assert len(db.get_notes()) == 1


def test_identifiant_inconnu_ne_depose_aucune_demande():
    """Un identifiant inconnu ne propose rien : l'outil le dit, et rien n'attend."""
    db.ajouter_note("Une note")

    assert outils.supprimer_note(9999) == "Aucune note trouvée avec l'identifiant 9999."
    assert outils.supprimer_note("abc") == "Aucune note trouvée avec l'identifiant abc."
    assert outils.supprimer_pense_bete(9999) == "Aucun pense-bête trouvé avec l'identifiant 9999."
    assert confirmation.en_attente() is None
    assert len(db.get_notes()) == 1


def test_pense_bete_suit_la_meme_regle():
    """Le retrait d'un pense-bête attend lui aussi le geste de l'utilisateur."""
    id_pb = db.ajouter_pense_bete("Rappeler le plombier")

    resultat = outils.executer_outil("supprimer_pense_bete", {"id_pense_bete": id_pb})

    assert resultat["statut"] == "confirmation_requise"
    assert len(db.get_pense_betes()) == 1
    demande = confirmation.en_attente()
    assert demande.type == confirmation.PENSE_BETE
    assert "Rappeler le plombier" in demande.libelle

    assert confirmation.confirmer() == f"Pense-bête n° {id_pb} retiré."
    assert db.get_pense_betes() == []


def test_oubli_confirme_vide_les_quatre_tables():
    """« Oublie-moi » ne fait rien tant que l'utilisateur n'a pas confirmé ; confirmé, il vide tout.

    Le périmètre complet (briefs, images, verrous) est testé dans test_oubli.py.
    """
    outils.enregistrer_profil(prenom="Bob", ville="Marseille")
    db.ajouter_note("Note secrète")
    db.sauvegarder_message("user", "Mon message privé")
    db.ajouter_pense_bete("Pense-bête privé")

    resultat = outils.executer_outil("oublier_utilisateur", {})

    assert resultat["statut"] == "confirmation_requise"
    assert db.get_profil() is not None
    assert len(db.get_notes()) == 1
    assert len(db.charger_historique()) == 1
    assert len(db.get_pense_betes()) == 1
    assert confirmation.en_attente().type == confirmation.TOUT

    confirmation.confirmer()

    assert db.get_profil() is None
    assert db.get_notes() == []
    assert db.charger_historique() == []
    assert db.get_pense_betes() == []
    # Le journal, lui, reste : il ne contient aucune donnée personnelle
    assert any(ligne["detail"] == "effacement confirmé" for ligne in lignes_confirmation())
    assert any(e["etape"] == "oubli" for e in journal.get_dernieres_activites())


def test_journal_sans_texte_de_note():
    """Le journal note la proposition, le refus et le retrait, jamais le texte."""
    id_note = db.ajouter_note("Rendez-vous médical confidentiel")
    outils.supprimer_note(id_note)
    confirmation.refuser()
    outils.supprimer_note(id_note)
    confirmation.confirmer()

    details = [ligne["detail"] for ligne in lignes_confirmation()]
    assert details == [
        "suppression proposée (note), en attente de confirmation",
        "suppression refusée (note)",
        "suppression proposée (note), en attente de confirmation",
        "note retirée",
    ]
    assert all("confidentiel" not in d for d in details)
    outils_lignes = [e for e in journal.get_dernieres_activites(limite=30) if e["etape"] == "outil:supprimer_note"]
    assert all("confidentiel" not in e["detail"] for e in outils_lignes)


def test_boucle_d_agent_rend_au_modele_une_attente(faux_gemini):
    """Quand le modèle demande l'outil dans la boucle, il reçoit « en attente », et rien n'est supprimé."""
    id_note = db.ajouter_note("Acheter du pain")
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="supprimer_note",
        arguments={"id_note": id_note},
        reponse_finale="Je te demande de confirmer.",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2]

    list(repondre("retire ma note sur le pain"))

    # Le résultat rendu au modèle au second tour dit que la suppression attend l'utilisateur
    resultat = faux_gemini.interactions.appels[1]["input"][0]["result"]
    assert resultat["statut"] == "confirmation_requise"
    assert len(db.get_notes()) == 1
    assert confirmation.en_attente().id == id_note


def test_page_web_confirme_par_le_bouton():
    """Le bouton de la page exécute la demande affichée, puis cache le cadre."""
    id_note = db.ajouter_note("Acheter du pain")
    outils.supprimer_note(id_note)

    cadre, question, chat, etat, valeur = confirmer_suppression()

    assert cadre == {"__type__": "update", "visible": False}
    assert question is None
    assert db.get_notes() == []
    assert confirmation.en_attente() is None


def test_page_web_annule_par_le_bouton():
    """Le bouton « Annuler » ne supprime rien et cache le cadre."""
    id_note = db.ajouter_note("Acheter du pain")
    outils.supprimer_note(id_note)

    cadre, question = annuler_suppression()

    assert cadre == {"__type__": "update", "visible": False}
    assert question is None
    assert len(db.get_notes()) == 1


def test_page_web_oubli_confirme_vide_le_chat():
    """Après un effacement confirmé par le bouton, le chat affiché est vidé."""
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    outils.oublier_utilisateur()

    _, _, chat, etat, valeur = confirmer_suppression()

    assert (chat, etat, valeur) == ([], [], [])
    assert db.get_profil() is None


def test_terminal_oui_supprime(monkeypatch):
    """Au terminal, c'est le programme qui pose la question, et « oui » supprime."""
    id_note = db.ajouter_note("Acheter du pain")
    outils.supprimer_note(id_note)
    questions = []

    def faux_input(invite):
        questions.append(invite)
        return "oui"

    monkeypatch.setattr("builtins.input", faux_input)

    chat_terminal.demander_confirmation(historique=[])

    assert len(questions) == 1
    assert "Supprimer la note" in questions[0]
    assert "Acheter du pain" in questions[0]
    assert db.get_notes() == []


def test_terminal_non_ne_supprime_rien(monkeypatch):
    """Au terminal, toute autre réponse que « oui » est un refus."""
    id_note = db.ajouter_note("Acheter du pain")
    outils.supprimer_note(id_note)
    monkeypatch.setattr("builtins.input", lambda invite: "")

    chat_terminal.demander_confirmation(historique=[])

    assert len(db.get_notes()) == 1
    assert confirmation.en_attente() is None


def test_terminal_sans_demande_ne_pose_aucune_question(monkeypatch):
    """Sans demande en attente, le terminal ne pose rien."""

    def input_interdit(invite):
        raise AssertionError("aucune question ne doit être posée")

    monkeypatch.setattr("builtins.input", input_interdit)

    chat_terminal.demander_confirmation(historique=[])


def test_terminal_oubli_confirme_vide_la_memoire_de_travail(monkeypatch):
    """Au terminal, un effacement confirmé vide aussi l'historique de la session."""
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    historique = [{"role": "user", "content": "Je m'appelle Zoe"}]
    outils.oublier_utilisateur()
    monkeypatch.setattr("builtins.input", lambda invite: "oui")

    chat_terminal.demander_confirmation(historique)

    assert historique == []
    assert db.get_profil() is None
