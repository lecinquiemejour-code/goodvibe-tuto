# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests de la mémoire de travail et de la mémoire de conversation.

Garanties :
- Ce qu'on montre n'est pas ce qu'on retient : les coulisses et le relevé ne repartent
  jamais au modèle avec l'historique, et ne sont jamais enregistrés dans conversations.
- Chaque test part de ce que la boucle d'agent produit vraiment au premier message,
  puis fait l'aller-retour par Gradio : jamais d'un historique écrit à la main.
"""

import gradio as gr

import chat_terminal
import db
import outils
from fragments import COULISSES, RELEVE, REPONSE, Fragment, avec_markdown
from interface import (
    MESSAGE_SANS_BRIEF,
    charger_page,
    chat_stream,
    extraire_texte,
    garder_la_confirmation,
    preparer_historique,
    vider_chat,
)
from tests.conftest import fabriquer_flux_outil, fabriquer_flux_texte
from vue_memoire import rafraichir_memoire


def historique_vu_par_gradio(message: str, messages_affiches: list) -> list:
    """Rend l'historique tel que Gradio le transmettra au message suivant.

    Fait passer les messages par le composant Chatbot, comme dans la page : le texte
    en ressort en liste de morceaux, et les messages marqués gardent leur titre.
    """
    chatbot = gr.Chatbot()
    affiche = chatbot.postprocess([{"role": "user", "content": message}, *messages_affiches])
    return chatbot.preprocess(affiche)


def test_extraire_texte_des_morceaux_gradio():
    """Vérifie que le texte est extrait des morceaux transmis par Gradio."""
    assert extraire_texte("salut") == "salut"
    assert extraire_texte([{"text": "salut", "type": "text"}]) == "salut"
    assert extraire_texte({"text": "salut", "type": "text"}) == "salut"
    # Un morceau qui n'est pas du texte (ex : un fichier) est ignoré
    assert extraire_texte([{"path": "image.png", "type": "file"}]) == ""
    assert extraire_texte(None) == ""


def test_page_web_second_message_sans_coulisses(faux_gemini):
    """Vérifie que l'entrée du second message ne contient que le dialogue.

    Reproduit le défaut constaté : la réponse affichée, coulisses comprises, revenait
    dans l'historique, et le prompt système partait deux fois.
    """
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("Bonjour !", inclure_reflexion=True),
        fabriquer_flux_texte("Avec plaisir."),
    ]

    messages = list(chat_stream("salut", [], voir_reflexion=True))[-1][0]
    # L'écran montre bien les coulisses et le relevé, en messages marqués
    titres = [m.metadata.get("title", "") for m in messages]
    assert any("Requête envoyée" in t for t in titres)
    assert any("Résumé de réflexion" in t for t in titres)
    assert any(t.startswith("Tokens :") for t in titres)

    historique = historique_vu_par_gradio("salut", messages)
    list(chat_stream("ok", historique, voir_reflexion=True))

    entree = faux_gemini.interactions.appels[1]["input"]
    assert entree == "User: salut\nAssistant: Bonjour !\nUser: ok"


def test_page_web_second_message_apres_un_outil(faux_gemini):
    """Vérifie que les JSON d'un appel d'outil ne repartent pas au modèle."""
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="enregistrer_profil",
        arguments={"prenom": "Zoe", "ville": "Lille"},
        reponse_finale="C'est bien noté Zoe !",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2, fabriquer_flux_texte("Avec plaisir.")]

    messages = list(chat_stream("Je m'appelle Zoe, de Lille.", [], voir_reflexion=True))[-1][0]
    assert any("Appel d'outil" in m.metadata.get("title", "") for m in messages)

    historique = historique_vu_par_gradio("Je m'appelle Zoe, de Lille.", messages)
    list(chat_stream("ok", historique, voir_reflexion=True))

    entree = faux_gemini.interactions.appels[2]["input"]
    assert entree == (
        "User: Je m'appelle Zoe, de Lille.\nAssistant: C'est bien noté Zoe !\nUser: ok"
    )


def test_page_web_enregistre_le_texte_seul(faux_gemini):
    """Vérifie que la table conversations ne reçoit ni coulisses, ni relevé, ni profil."""
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("Bonjour !", inclure_reflexion=True)
    ]

    list(chat_stream("salut", [], voir_reflexion=True))

    assert db.charger_historique() == [
        {"role": "user", "content": "salut"},
        {"role": "assistant", "content": "Bonjour !"},
    ]


def test_page_web_flux_dans_son_panneau(faux_gemini):
    """Vérifie que le flux brut va dans son panneau, et nulle part ailleurs.

    Ni message dans le chat, ni ligne dans conversations, ni retour au modèle.
    """
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="enregistrer_profil",
        arguments={"prenom": "Zoe", "ville": "Lille"},
        reponse_finale="C'est bien noté Zoe !",
    )
    attendu = {
        "Tour 1": [e.model_dump() for e in tour1],
        "Tour 2": [e.model_dump() for e in tour2],
    }
    faux_gemini.interactions.scenarios = [tour1, tour2, fabriquer_flux_texte("Avec plaisir.")]

    etapes = list(chat_stream("Je m'appelle Zoe, de Lille.", [], voir_reflexion=True))

    # Le panneau se remplit au fil de l'eau : un événement de plus à chaque arrivée
    tailles = [sum(len(evenements) for evenements in flux.values()) for _, _, flux in etapes]
    assert tailles == sorted(tailles)
    messages, _, flux = etapes[-1]
    assert flux == attendu

    # Le chat garde sa réponse en un seul message, sans message venu du flux
    reponses = [m.content for m in messages if not m.metadata.get("title")]
    assert reponses == ["C'est bien noté Zoe !"]
    assert db.charger_historique() == [
        {"role": "user", "content": "Je m'appelle Zoe, de Lille."},
        {"role": "assistant", "content": "C'est bien noté Zoe !"},
    ]

    historique = historique_vu_par_gradio("Je m'appelle Zoe, de Lille.", messages)
    list(chat_stream("ok", historique, voir_reflexion=True))
    entree = faux_gemini.interactions.appels[2]["input"]
    assert entree == (
        "User: Je m'appelle Zoe, de Lille.\nAssistant: C'est bien noté Zoe !\nUser: ok"
    )


def test_page_web_panneau_vide_coulisses_fermees(faux_gemini):
    """Vérifie que, case décochée, le panneau du flux reste vide."""
    faux_gemini.interactions.scenarios = [fabriquer_flux_texte("Bonjour !")]

    etapes = list(chat_stream("salut", [], voir_reflexion=False))

    assert all(flux == {} for _, _, flux in etapes)


def test_preparer_historique_ecarte_les_messages_marques():
    """Vérifie que le tri se fait sur la marque du message, sans lire son texte."""
    historique = [
        {"role": "user", "content": [{"text": "salut", "type": "text"}], "metadata": None},
        {
            "role": "assistant",
            "content": [{"text": "Bonjour !", "type": "text"}],
            "metadata": {"title": "Un titre quelconque"},
        },
        {"role": "assistant", "content": [{"text": "Bonjour !", "type": "text"}], "metadata": {}},
    ]

    assert preparer_historique(historique) == [
        {"role": "user", "content": "salut"},
        {"role": "assistant", "content": "Bonjour !"},
    ]
    # L'historique reçu reste intact : la page web s'en sert pour l'affichage
    assert len(historique) == 3


def test_terminal_second_message_sans_coulisses(faux_gemini, monkeypatch):
    """Vérifie la même garantie au terminal, qui tient son propre historique."""
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("Bonjour !", inclure_reflexion=True),
        fabriquer_flux_texte("Avec plaisir."),
    ]
    saisies = iter(["salut", "ok", "quitte"])
    monkeypatch.setattr("builtins.input", lambda _: next(saisies))
    monkeypatch.setattr(chat_terminal, "verifier_config", lambda: None)

    chat_terminal.lancer_chat()

    entree = faux_gemini.interactions.appels[1]["input"]
    assert entree == "User: salut\nAssistant: Bonjour !\nUser: ok"
    assert [m["content"] for m in db.charger_historique()] == [
        "salut",
        "Bonjour !",
        "ok",
        "Avec plaisir.",
    ]


def test_en_tete_de_reponse_hors_de_la_reponse():
    """Vérifie que l'en-tête « Réponse de GoodVibe » s'affiche sans entrer dans la réponse."""
    fragments = [
        Fragment(nature=COULISSES, titre="💭 Résumé de réflexion :", texte="..."),
        Fragment(nature=REPONSE, texte="Bonjour"),
        Fragment(nature=REPONSE, texte=" !"),
        Fragment(nature=RELEVE, texte="Tokens : 10 entrée"),
    ]

    couples = list(avec_markdown(fragments))

    affiche = "".join(texte for _, texte in couples)
    assert affiche.count("Réponse de GoodVibe") == 1
    assert "*Tokens : 10 entrée*" in affiche
    retenu = "".join(f.texte for f, _ in couples if f.nature == REPONSE)
    assert retenu == "Bonjour !"


def test_page_relit_la_base_a_chaque_ouverture():
    """Vérifie que la page affiche l'état actuel de la base, pas une photographie du démarrage."""
    assert charger_page()[0] == []

    db.sauvegarder_message("user", "salut")
    db.sauvegarder_message("assistant", "Bonjour !")
    db.sauvegarder_brief(contenu="Brief du jour", date_jour="2026-09-29")

    historique, etat, valeur, _, texte_brief = charger_page()
    assert historique == [
        {"role": "user", "content": "salut"},
        {"role": "assistant", "content": "Bonjour !"},
    ]
    # L'affichage et les deux mémoires internes du chat reçoivent le même historique
    assert etat == historique
    assert valeur == historique
    assert texte_brief == "Brief du jour"


def test_page_vide_apres_oubli_par_le_bouton():
    """Vérifie qu'une conversation effacée ne réapparaît pas au rechargement de la page."""
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    db.sauvegarder_message("user", "Je m'appelle Zoe")
    db.sauvegarder_message("assistant", "Enchanté Zoe !")

    # Le bouton « Oublie-moi » de l'onglet Mémoire appelle cette fonction
    db.effacer_donnees_utilisateur()

    assert charger_page()[0] == []
    assert vider_chat() == ([], [], [])


def test_echange_enregistre_apres_oubli_par_le_bouton(faux_gemini):
    """Vérifie que le premier échange qui suit un clic sur « Oublie-moi » est enregistré.

    Le bouton n'efface pas au milieu d'un échange : il n'y a rien à ignorer ensuite.
    """
    faux_gemini.interactions.scenarios = [fabriquer_flux_texte("Bonjour !")]
    db.effacer_donnees_utilisateur()

    list(chat_stream("salut", [], voir_reflexion=False))

    assert [m["content"] for m in db.charger_historique()] == ["salut", "Bonjour !"]


def test_echange_ignore_apres_oubli_dans_le_chat(faux_gemini):
    """Vérifie que l'échange qui contient la demande d'oubli n'est pas enregistré.

    L'outil efface au milieu de l'échange : sans verrou, la demande d'oubli et sa
    réponse seraient réécrites dans la table juste après l'effacement.
    """
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("C'est fait, je ne sais plus rien de toi."),
        fabriquer_flux_texte("Bonjour !"),
    ]
    outils.oublier_utilisateur()

    list(chat_stream("oui, efface tout", [], voir_reflexion=False))
    assert db.charger_historique() == []

    # L'échange suivant est enregistré normalement
    list(chat_stream("salut", [], voir_reflexion=False))
    assert [m["content"] for m in db.charger_historique()] == ["salut", "Bonjour !"]


def test_page_sans_brief():
    """Vérifie le message affiché tant qu'aucun brief n'a été produit."""
    assert charger_page()[4] == MESSAGE_SANS_BRIEF


def test_oubli_dans_le_chat_vide_la_conversation_affichee(faux_gemini):
    """Vérifie qu'après un oubli demandé dans le chat, seule la confirmation reste à l'écran.

    Sans cela, la conversation effacée de la base resterait affichée, et repartirait
    au modèle au message suivant.
    """
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="oublier_utilisateur",
        arguments={},
        reponse_finale="C'est fait, je ne sais plus rien de toi.",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2]
    avant = [
        {"role": "user", "content": [{"text": "Je m'appelle Zoe", "type": "text"}], "metadata": None},
        {"role": "assistant", "content": [{"text": "Enchanté Zoe !", "type": "text"}], "metadata": {}},
    ]

    etapes = list(chat_stream("oui, efface tout", avant, voir_reflexion=True))

    # Le signal n'est levé qu'à la fin de la réponse
    assert [oubli for _, oubli, _ in etapes[:-1]] == [False] * (len(etapes) - 1)
    messages, oubli, _ = etapes[-1]
    assert oubli is True
    assert db.get_profil() is None

    affichage = historique_vu_par_gradio("oui, efface tout", messages)
    garde, etat, valeur, signal = garder_la_confirmation(True, avant + affichage)
    assert [extraire_texte(m["content"]) for m in garde] == [
        "C'est fait, je ne sais plus rien de toi."
    ]
    assert etat == garde
    assert valeur == garde
    assert signal is False


def test_echange_ordinaire_ne_leve_pas_le_signal(faux_gemini):
    """Vérifie qu'un échange sans oubli laisse la conversation affichée intacte."""
    faux_gemini.interactions.scenarios = [fabriquer_flux_texte("Bonjour !")]

    etapes = list(chat_stream("salut", [], voir_reflexion=False))

    assert all(oubli is False for _, oubli, _ in etapes)


def test_tableaux_memoire_relus_a_la_demande():
    """Vérifie que l'onglet Mémoire lit les quatre tableaux, dans l'état actuel de la base."""
    assert rafraichir_memoire() == ([], [], [], [])

    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    profil, notes, conversations, pense_betes = rafraichir_memoire()
    assert profil[0][1] == "Zoe"

    db.effacer_donnees_utilisateur()
    assert rafraichir_memoire() == ([], [], [], [])
