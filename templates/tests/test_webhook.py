# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests automatisés du webhook de réception des pense-bêtes (Feature 14).

Vérifie :
- L'authentification par jeton secret X-Token (202 avec bon jeton, 401 sans ou avec mauvais jeton).
- L'ordre : le pense-bête est en base avant la réponse, qui est un 202 Accepted avec le
  statut « enregistre », le message et l'identifiant.
- Le déclenchement du brief du jour (recette du bouton, forcer=True, déclencheur « webhook »)
  en tâche de fond ; en cas d'échec de la recette, le webhook survit, le pense-bête passe en
  échec et reste repris par le brief suivant. L'encadrement de la recette dans le journal
  est testé dans test_journal_brief.py.
- Les restrictions de sécurité CORS pour Hoppscotch.
- L'effacement complet des pense-bêtes lors de l'action « oublie-moi ».
- Le cycle d'intégration et de marquage dans le brief matinal.
- Zéro appel réseau externe : la recette du brief est simulée dans tous les tests.
"""

import pytest
from fastapi.testclient import TestClient

import config
import db
import journal
import webhook
from webhook import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def recette_simulee(monkeypatch):
    """Remplace la recette du brief par un simulacre pour tous les tests du webhook.

    Le client de test exécute les tâches de fond immédiatement : sans ce simulacre,
    chaque 202 lancerait un vrai brief (modèle, image), ce que ni le test ni la CI
    ne doivent faire. Le simulacre note chaque appel avec ses arguments et l'état
    de la table des pense-bêtes au moment de l'appel.
    """
    appels = []

    def faux_generer_brief(forcer=False, declencheur=None):
        appels.append(
            {
                "forcer": forcer,
                "declencheur": declencheur,
                "pense_betes_en_attente": db.get_pense_betes(non_integres_seulement=True),
            }
        )
        return "brief simulé"

    monkeypatch.setattr(webhook, "generer_brief", faux_generer_brief)
    return appels


def test_webhook_enregistre_puis_repond_202_puis_declenche_le_brief(monkeypatch, recette_simulee):
    """Vérifie l'ordre : en base, réponse 202 avec l'identifiant, puis la recette avec forcer=True."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    reponse = client.post(
        "/pense-bete",
        headers={"X-Token": "jeton-secret-test-xyz"},
        json={"texte": "Rappeler le plombier"},
    )

    assert reponse.status_code == 202
    corps = reponse.json()
    assert corps["statut"] == "enregistre"
    assert corps["message"] == "Pense-bête enregistré. Génération du brief en attente."
    # L'identifiant rendu est celui de la ligne en base
    enregistres = db.get_pense_betes()
    assert [pb["id"] for pb in enregistres] == [corps["id"]]
    assert enregistres[0]["texte"] == "Rappeler le plombier"

    assert len(recette_simulee) == 1
    assert recette_simulee[0]["forcer"] is True
    # La recette reçoit le nom de son déclencheur : c'est elle qui l'écrit au journal
    assert recette_simulee[0]["declencheur"] == "webhook"
    # Au moment de l'appel, le pense-bête était déjà en base : le brief le contiendra
    textes = [pb["texte"] for pb in recette_simulee[0]["pense_betes_en_attente"]]
    assert textes == ["Rappeler le plombier"]

    # L'enregistrement est journalisé, sans le texte du pense-bête
    lignes = [e for e in journal.get_dernieres_activites(limite=10) if e["etape"] == "webhook"]
    assert len(lignes) == 1
    assert lignes[0]["detail"] == "pense-bête enregistré"
    assert "plombier" not in lignes[0]["detail"]


def test_statut_integre_apres_un_brief_reussi(monkeypatch):
    """Vérifie que la recette, en marquant le pense-bête, le fait passer à « intégré »."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    def recette_qui_integre(forcer=False, declencheur=None):
        en_attente = db.get_pense_betes(non_integres_seulement=True)
        db.marquer_pense_betes_integres([pb["id"] for pb in en_attente])
        return "brief simulé"

    monkeypatch.setattr(webhook, "generer_brief", recette_qui_integre)

    reponse = client.post(
        "/pense-bete",
        headers={"X-Token": "jeton-secret-test-xyz"},
        json={"texte": "Dentiste à 10 h"},
    )

    assert reponse.status_code == 202
    assert db.get_pense_betes()[0]["statut"] == db.STATUT_INTEGRE
    assert db.get_pense_betes(non_integres_seulement=True) == []


def test_webhook_sans_jeton_ne_declenche_pas_le_brief(monkeypatch, recette_simulee):
    """Vérifie qu'un refus 401 ne lance aucune génération."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    reponse = client.post("/pense-bete", json={"texte": "Rappeler le plombier"})

    assert reponse.status_code == 401
    assert recette_simulee == []


def test_webhook_survit_a_un_echec_du_brief(monkeypatch):
    """Vérifie qu'un échec de la recette ne casse pas le webhook, et laisse le pense-bête en échec.

    L'appelant a déjà reçu son 202. La recette a noté l'échec au journal (voir
    test_journal_brief.py) ; ici on vérifie que la tâche de fond ne fait pas tomber
    le service, que le pense-bête passe en échec, et qu'il reste repris par le brief suivant.
    """
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    def recette_en_panne(forcer=False, declencheur=None):
        raise RuntimeError("modèle indisponible")

    monkeypatch.setattr(webhook, "generer_brief", recette_en_panne)

    reponse = client.post(
        "/pense-bete",
        headers={"X-Token": "jeton-secret-test-xyz"},
        json={"texte": "Dentiste à 10 h"},
    )

    assert reponse.status_code == 202
    assert reponse.json()["statut"] == "enregistre"

    tous = db.get_pense_betes()
    assert len(tous) == 1
    assert tous[0]["statut"] == db.STATUT_ECHEC
    # Le brief suivant le reprend
    a_reprendre = db.get_pense_betes(non_integres_seulement=True)
    assert [pb["texte"] for pb in a_reprendre] == ["Dentiste à 10 h"]


def test_webhook_succes_avec_bon_jeton(monkeypatch):
    """Vérifie qu'une requête avec le bon jeton renvoie 202 et que le pense-bête est en base, en attente."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    reponse = client.post(
        "/pense-bete",
        headers={"X-Token": "jeton-secret-test-xyz"},
        json={"texte": "Dentiste mardi à 10 h"},
    )

    assert reponse.status_code == 202
    assert set(reponse.json()) == {"statut", "message", "id"}

    pense_betes = db.get_pense_betes(non_integres_seulement=True)
    assert len(pense_betes) == 1
    assert pense_betes[0]["texte"] == "Dentiste mardi à 10 h"
    assert pense_betes[0]["statut"] == db.STATUT_EN_ATTENTE


def test_webhook_echec_sans_jeton(monkeypatch):
    """Vérifie le rejet 401 si l'en-tête X-Token est absent."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    reponse = client.post(
        "/pense-bete",
        json={"texte": "Rappeler le plombier"},
    )

    assert reponse.status_code == 401
    assert "invalide ou manquant" in reponse.json()["detail"]
    # Rien n'est enregistré
    assert len(db.get_pense_betes()) == 0


def test_webhook_echec_mauvais_jeton(monkeypatch):
    """Vérifie le rejet 401 si l'en-tête X-Token contient une valeur erronée."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    reponse = client.post(
        "/pense-bete",
        headers={"X-Token": "mauvais-jeton-faux"},
        json={"texte": "Rappeler le plombier"},
    )

    assert reponse.status_code == 401
    assert "invalide ou manquant" in reponse.json()["detail"]
    assert len(db.get_pense_betes()) == 0


def test_webhook_echec_jeton_non_configure(monkeypatch):
    """Vérifie le rejet 401 si WEBHOOK_TOKEN n'est pas configuré sur le serveur."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "")

    reponse = client.post(
        "/pense-bete",
        headers={"X-Token": "nimporte-quoi"},
        json={"texte": "Message test"},
    )

    assert reponse.status_code == 401
    assert len(db.get_pense_betes()) == 0


def test_webhook_validation_taille_texte(monkeypatch):
    """Vérifie le rejet 422 si le texte est vide ou dépasse 1000 caractères."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    # Texte vide
    reponse_vide = client.post(
        "/pense-bete",
        headers={"X-Token": "jeton-secret-test-xyz"},
        json={"texte": ""},
    )
    assert reponse_vide.status_code == 422

    # Texte trop long (> 1000 caractères)
    reponse_trop_long = client.post(
        "/pense-bete",
        headers={"X-Token": "jeton-secret-test-xyz"},
        json={"texte": "a" * 1001},
    )
    assert reponse_trop_long.status_code == 422
    # Le contenu est vérifié avant l'enregistrement : rien n'est en base
    assert db.get_pense_betes() == []


def test_webhook_cors_autorise_hoppscotch(monkeypatch):
    """Vérifie que CORS autorise explicitement l'origine https://hoppscotch.io."""
    monkeypatch.setattr(config, "WEBHOOK_TOKEN", "jeton-secret-test-xyz")

    reponse = client.options(
        "/pense-bete",
        headers={
            "Origin": "https://hoppscotch.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Token,Content-Type",
        },
    )

    assert reponse.status_code == 200
    assert reponse.headers.get("access-control-allow-origin") == "https://hoppscotch.io"


def test_pense_betes_effaces_par_oublie_moi():
    """Vérifie que effacer_donnees_utilisateur vide également la table pense_betes."""
    db.ajouter_pense_bete("Pense-bête avant oubli")
    assert len(db.get_pense_betes()) == 1

    db.effacer_donnees_utilisateur()

    assert len(db.get_pense_betes()) == 0


def test_cycle_integration_pense_betes():
    """Vérifie la distinction entre pense-bêtes en attente et pense-bêtes intégrés."""
    id1 = db.ajouter_pense_bete("Mémo 1")
    id2 = db.ajouter_pense_bete("Mémo 2")

    en_attente = db.get_pense_betes(non_integres_seulement=True)
    assert len(en_attente) == 2
    assert [pb["id"] for pb in en_attente] == [id1, id2]

    # Marquer le premier comme intégré
    db.marquer_pense_betes_integres([id1])

    reste_en_attente = db.get_pense_betes(non_integres_seulement=True)
    assert len(reste_en_attente) == 1
    assert reste_en_attente[0]["id"] == id2

    # L'ensemble des pense-bêtes reste présent dans la table complète
    tous = db.get_pense_betes(non_integres_seulement=False)
    assert len(tous) == 2
    assert {pb["id"]: pb["statut"] for pb in tous} == {id1: db.STATUT_INTEGRE, id2: db.STATUT_EN_ATTENTE}

    # Un pense-bête en échec est repris lui aussi ; un pense-bête intégré ne repasse jamais en échec
    db.marquer_pense_bete_echec(id2)
    db.marquer_pense_bete_echec(id1)
    assert [pb["id"] for pb in db.get_pense_betes(non_integres_seulement=True)] == [id2]
    assert {pb["id"]: pb["statut"] for pb in db.get_pense_betes()} == {id1: db.STATUT_INTEGRE, id2: db.STATUT_ECHEC}


def test_supprimer_pense_bete_succes():
    """Vérifie la suppression d'un pense-bête par son identifiant, après confirmation de l'utilisateur."""
    import confirmation
    import outils

    id_pb = db.ajouter_pense_bete("Pense-bête à supprimer")
    assert len(db.get_pense_betes()) == 1

    # L'outil propose, et ne supprime pas
    resultat = outils.supprimer_pense_bete(id_pb)
    assert resultat["statut"] == "confirmation_requise"
    assert len(db.get_pense_betes()) == 1

    # Le geste de l'utilisateur supprime
    assert confirmation.confirmer() == f"Pense-bête n° {id_pb} retiré."
    assert len(db.get_pense_betes()) == 0

    # Vérification que le journal d'activité ne fait fuiter aucune donnée personnelle
    import journal

    entrees = journal.get_dernieres_activites(limite=5)
    dernieres_actions = [e for e in entrees if e["etape"] == "outil:supprimer_pense_bete"]
    assert len(dernieres_actions) >= 1
    assert dernieres_actions[0]["detail"] == "Suppression d'un pense-bête proposée, en attente de confirmation"
    assert "Pense-bête à supprimer" not in dernieres_actions[0]["detail"]


def test_supprimer_pense_bete_introuvable():
    """Vérifie le message d'erreur lorsqu'un ID de pense-bête n'existe pas."""
    import outils

    message = outils.supprimer_pense_bete(99999)
    assert "Aucun pense-bête trouvé avec l'identifiant 99999." in message


def test_lire_pense_betes_outil():
    """Vérifie que l'outil lire_pense_betes renvoie la liste complète."""
    import outils

    id1 = db.ajouter_pense_bete("Mémo A")
    id2 = db.ajouter_pense_bete("Mémo B")

    resultat = outils.lire_pense_betes()
    assert len(resultat) == 2
    ids = [pb["id"] for pb in resultat]
    assert id1 in ids and id2 in ids
    textes = [pb["texte"] for pb in resultat]
    assert "Mémo A" in textes
    assert "Mémo B" in textes

    # Aiguillage via executer_outil : la suppression est proposée, puis confirmée
    import confirmation

    rep = outils.executer_outil("supprimer_pense_bete", {"id_pense_bete": id1})
    assert rep["statut"] == "confirmation_requise"
    assert len(db.get_pense_betes()) == 2
    confirmation.confirmer()
    assert [pb["id"] for pb in db.get_pense_betes()] == [id2]

