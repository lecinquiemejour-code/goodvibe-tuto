# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires de la boucle d'agent autonome (agent.py).

Garanties :
- Aucun appel à Google Gemini réel (flux d'interactions mocké).
- Vérification du streaming, des tours d'outils et du garde-fou MAX_TOURS.
- Vérification de l'enregistrement de l'activité technique au journal.
"""

import db
from agent import repondre
from fragments import COULISSES, FLUX, RELEVE, REPONSE
from tests.conftest import (
    MockDelta,
    MockEvent,
    MockInteraction,
    MockStep,
    MockUsage,
    fabriquer_flux_outil,
    fabriquer_flux_texte,
)


def texte_de(fragments, nature=REPONSE):
    """Recolle le texte des fragments d'une nature donnée."""
    return "".join(f.texte for f in fragments if f.nature == nature)


def test_agent_reponse_texte_streaming(faux_gemini):
    """Vérifie le streaming d'une réponse texte directe sans outil."""
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("Bonjour ! Je suis GoodVibe.", tokens_in=50, tokens_out=25)
    ]

    fragments = list(repondre("Bonjour"))

    # La réponse ne contient que le propos : le relevé est un fragment à part
    assert texte_de(fragments) == "Bonjour ! Je suis GoodVibe."
    releves = [f for f in fragments if f.nature == RELEVE]
    assert len(releves) == 1
    assert "Premier mot :" in releves[0].texte
    assert releves[0].chiffres["tokens_entree"] == 50
    assert releves[0].chiffres["tokens_sortie"] == 25
    assert releves[0].chiffres["tours"] == 1


def test_agent_etiquette_chaque_fragment(faux_gemini):
    """Vérifie la séparation à la source : coulisses, réponse et relevé sont distincts."""
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="enregistrer_profil",
        arguments={"prenom": "Zoe", "ville": "Lille"},
        reponse_finale="C'est bien noté Zoe !",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2]

    fragments = list(repondre("Je m'appelle Zoe et j'habite à Lille.", voir_reflexion=True))

    titres = [f.titre for f in fragments if f.nature == COULISSES]
    assert any("Requête envoyée" in t for t in titres)
    assert any("Appel d'outil" in t for t in titres)
    # Ni JSON, ni prompt système, ni relevé dans le texte de la réponse
    assert texte_de(fragments) == "C'est bien noté Zoe !"
    assert [f.chiffres["tours"] for f in fragments if f.nature == RELEVE] == [2]


def test_agent_coulisses_fermees(faux_gemini):
    """Vérifie que, coulisses fermées, aucun fragment de coulisses n'est émis."""
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("Bonjour !", inclure_reflexion=True)
    ]

    fragments = list(repondre("Bonjour", voir_reflexion=False))

    assert [f.nature for f in fragments] == [REPONSE, RELEVE]


def test_agent_flux_un_fragment_par_evenement(faux_gemini):
    """Vérifie que chaque événement reçu de Gemini sort tel quel, avec son numéro de tour."""
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="enregistrer_profil",
        arguments={"prenom": "Zoe", "ville": "Lille"},
        reponse_finale="C'est bien noté Zoe !",
    )
    # Le faux client vide ses scénarios en les servant : on compte avant l'appel
    attendus = [e.model_dump() for e in tour1] + [e.model_dump() for e in tour2]
    faux_gemini.interactions.scenarios = [tour1, tour2]

    fragments = list(repondre("Je m'appelle Zoe et j'habite à Lille.", voir_flux=True))

    flux = [f for f in fragments if f.nature == FLUX]
    assert [f.evenement for f in flux] == attendus
    assert [f.tour for f in flux] == [1] * len(tour1) + [2] * len(tour2)
    # Le flux ne porte aucun texte : rien de lui n'entre dans la réponse
    assert all(f.texte == "" for f in flux)
    assert texte_de(fragments) == "C'est bien noté Zoe !"


def test_agent_sans_flux_si_personne_ne_le_demande(faux_gemini):
    """Vérifie que, sans demande explicite, aucun fragment de flux n'est émis.

    Le terminal et le brief automatique n'ont pas de panneau : ils ne le demandent pas,
    même coulisses ouvertes.
    """
    faux_gemini.interactions.scenarios = [
        fabriquer_flux_texte("Bonjour !", inclure_reflexion=True)
    ]

    fragments = list(repondre("Bonjour", voir_reflexion=True))

    assert [f for f in fragments if f.nature == FLUX] == []


def test_agent_appel_outil_autonome(faux_gemini):
    """Vérifie qu'un appel d'outil déclenché par Gemini s'exécute puis poursuit la boucle."""
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="enregistrer_profil",
        arguments={"prenom": "Zoe", "ville": "Lille"},
        reponse_finale="C'est bien noté Zoe, j'ai enregistré votre ville Lille !",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2]

    fragments = list(repondre("Je m'appelle Zoe et j'habite à Lille."))

    assert "C'est bien noté Zoe" in texte_de(fragments)
    # Vérifie que la base en mémoire a bien été mise à jour par l'outil
    profil = db.get_profil()
    assert profil is not None
    assert profil["prenom"] == "Zoe"
    assert profil["ville"] == "Lille"


def test_agent_renvoie_prompt_systeme_et_outils_a_chaque_tour(faux_gemini):
    """Vérifie que le prompt système, le profil et les outils partent aussi au second tour.

    L'API Interactions ne conserve d'un appel à l'autre que la conversation. Si le second
    appel part sans prompt système, le modèle rédige sans connaître le prénom de
    l'utilisateur et en invente un.
    """
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion")
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="lire_notes",
        arguments={},
        reponse_finale="Bonjour Zoe !",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2]

    list(repondre("Prépare mon brief"))

    appels = faux_gemini.interactions.appels
    assert len(appels) == 2

    # Le second appel enchaîne sur le premier...
    second_appel = appels[1]
    assert second_appel.get("previous_interaction_id")

    # ... et renvoie quand même le prompt système, le profil et les outils
    assert "Prénom: Zoe" in second_appel.get("system_instruction", "")
    assert second_appel.get("tools")
    assert second_appel["system_instruction"] == appels[0]["system_instruction"]


def test_prompt_systeme_sans_donnee_personnelle(faux_gemini):
    """Vérifie que, sans profil en mémoire, aucun prénom n'est envoyé au modèle.

    Le fichier prompt_systeme.md est enregistré dans le dépôt : il ne doit contenir
    aucune donnée personnelle, pas même un prénom dans un exemple.
    """
    faux_gemini.interactions.scenarios = [fabriquer_flux_texte("Bonjour !")]

    list(repondre("Bonjour"))

    prompt_envoye = faux_gemini.interactions.appels[0]["system_instruction"]
    assert "Prénom:" not in prompt_envoye
    # Sans profil ni note, la section mémoire n'est pas ajoutée au prompt système
    assert "### Mémoire actuelle de GoodVibe :" not in prompt_envoye


def test_agent_garde_fou_max_tours(faux_gemini, monkeypatch):
    """Vérifie que la boucle d'agent s'interrompt de force quand MAX_TOURS est atteint."""
    import agent
    import config
    monkeypatch.setattr(config, "MAX_TOURS", 2)
    monkeypatch.setattr(agent, "MAX_TOURS", 2)

    # Scénario où le modèle demande sans cesse des outils
    call_step = MockStep(step_type="function_call", step_id="call_inf", name="lire_notes")
    tour_infini = [
        MockEvent(step=call_step),
        MockEvent(delta=MockDelta(delta_type="arguments_delta", arguments="{}")),
        MockEvent(event_type="step.stop"),
        MockEvent(
            event_type="interaction.completed",
            interaction=MockInteraction("inter_inf", MockUsage(20, 10, 0)),
        ),
    ]

    faux_gemini.interactions.scenarios = [tour_infini, tour_infini, tour_infini]

    fragments = list(repondre("Boucle infinie"))

    assert "[Arrêt de sécurité : nombre maximal de tours atteint]" in texte_de(fragments)


def test_conversation_recoit_tous_les_outils(faux_gemini):
    """Vérifie qu'en conversation, sans liste d'outils autorisés, le catalogue complet part au modèle."""
    faux_gemini.interactions.scenarios = [fabriquer_flux_texte("Bonjour !")]

    list(repondre("Bonjour"))

    noms = [o["name"] for o in faux_gemini.interactions.appels[0]["tools"]]
    for attendu in ("enregistrer_profil", "ecrire_note", "supprimer_note", "oublier_utilisateur", "meteo", "fetch"):
        assert attendu in noms


def test_liste_autorisee_filtre_le_catalogue_et_refuse_l_execution(faux_gemini):
    """Vérifie les deux barrières : l'outil hors liste ne part pas, et ne s'exécute pas s'il est demandé."""
    import confirmation
    import journal

    id_note = db.ajouter_note("Note à protéger")
    tour1, tour2 = fabriquer_flux_outil(
        nom_outil="supprimer_note",
        arguments={"id_note": id_note},
        reponse_finale="Je n'ai pas pu supprimer.",
    )
    faux_gemini.interactions.scenarios = [tour1, tour2]

    fragments = list(repondre("Prépare mon brief", voir_reflexion=True, outils_autorises=["meteo", "lire_notes"]))

    # Première barrière : le catalogue transmis ne contient que la liste
    noms = sorted(o["name"] for o in faux_gemini.interactions.appels[0]["tools"])
    assert noms == ["lire_notes", "meteo"]
    # Seconde barrière : l'outil demandé quand même n'est pas exécuté
    assert len(db.get_notes()) == 1
    assert confirmation.en_attente() is None
    resultat = faux_gemini.interactions.appels[1]["input"][0]["result"]
    assert resultat["message"].startswith("Erreur : l'outil supprimer_note n'est pas disponible")
    # Le refus se voit dans les coulisses et dans le journal
    assert any(f.nature == COULISSES and "n'est pas disponible" in f.texte for f in fragments)
    refus = [e for e in journal.get_dernieres_activites() if e["etape"] == "outil:supprimer_note"]
    assert refus and refus[0]["detail"].startswith("Appel refusé")


def test_prompt_systeme_introuvable_rend_un_message_d_erreur(faux_gemini, monkeypatch, tmp_path):
    """Vérifie que, sans sa fiche de poste, GoodVibe le dit et n'appelle pas le modèle.

    Aucune phrase de secours n'existe dans le code : sans ses règles, il ne répond pas.
    """
    import config

    monkeypatch.setattr(config, "PROMPT_SYSTEME_PATH", tmp_path / "prompt_systeme.md")

    fragments = list(repondre("Bonjour"))

    assert "prompt_systeme.md est introuvable" in texte_de(fragments)
    assert "ne peut pas répondre sans sa fiche de poste" in texte_de(fragments)
    assert faux_gemini.interactions.appels == []
    echecs = [a for a in db.get_connection().execute("SELECT detail FROM journal").fetchall()]
    assert any("prompt_systeme.md est introuvable" in ligne["detail"] for ligne in echecs)
