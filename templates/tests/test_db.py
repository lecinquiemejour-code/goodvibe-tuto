# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du gestionnaire de base de données SQLite (db.py).

Garantit le bon fonctionnement du stockage local en mémoire :
- Gestion du profil et des mises à jour partielles
- Gestion des notes
- Gestion de l'historique de conversation
- Verrou anti-doublon et persistance des briefs
- Grille tarifaire configurable
"""

import db


def test_profil_creation_et_mise_a_jour_partielle():
    """Vérifie la création initiale puis la mise à jour partielle du profil."""
    assert db.get_profil() is None

    # Création initiale
    db.sauvegarder_profil(prenom="Claire", ville="Nantes")
    profil = db.get_profil()
    assert profil is not None
    assert profil["prenom"] == "Claire"
    assert profil["ville"] == "Nantes"
    assert profil["signe"] is None

    # Mise à jour partielle (ajout du signe sans perdre le prénom ni la ville)
    db.sauvegarder_profil(signe="Balance")
    profil_maj = db.get_profil()
    assert profil_maj["prenom"] == "Claire"
    assert profil_maj["ville"] == "Nantes"
    assert profil_maj["signe"] == "Balance"


def test_historique_conversations():
    """Vérifie l'enregistrement et le chargement dans l'ordre chronologique."""
    db.sauvegarder_message("user", "Hello GoodVibe !")
    db.sauvegarder_message("assistant", "Bonjour ! Comment allez-vous ?")

    historique = db.charger_historique()
    assert len(historique) == 2
    assert historique[0]["role"] == "user"
    assert historique[0]["content"] == "Hello GoodVibe !"
    assert historique[1]["role"] == "assistant"
    assert historique[1]["content"] == "Bonjour ! Comment allez-vous ?"


def test_verrou_anti_doublon_traites():
    """Vérifie le fonctionnement de la table 'traites' pour l'anti-doublon."""
    cle = "brief:2026-09-28"
    assert not db.est_deja_traite(cle)

    db.marquer_traite(cle)
    assert db.est_deja_traite(cle)
    assert not db.est_deja_traite("brief:2026-09-29")


def test_sauvegarde_et_lecture_brief():
    """Vérifie l'enregistrement et la lecture du dernier brief."""
    id_brief = db.sauvegarder_brief(contenu="Mon brief du matin ensoleillé.", date_jour="2026-09-28")
    assert id_brief > 0

    dernier = db.get_dernier_brief()
    assert dernier is not None
    assert dernier["date"] == "2026-09-28"
    assert "ensoleillé" in dernier["contenu"]


def test_tarifs_configurables():
    """Vérifie qu'une base neuve n'a aucun prix, puis la saisie de la grille par le pilote."""
    # Aucun prix n'est écrit d'avance dans le code
    assert db.get_tarifs() is None

    # Saisie de la grille
    db.sauvegarder_tarifs(
        prix_entree_usd=0.15,
        prix_sortie_usd=0.60,
        prix_reflexion_usd=0.60,
        prix_image_usd=0.04,
    )
    tarifs_maj = db.get_tarifs()
    assert tarifs_maj["prix_entree_usd"] == 0.15
    assert tarifs_maj["prix_sortie_usd"] == 0.60
    assert tarifs_maj["prix_image_usd"] == 0.04


def test_migration_statut_des_pense_betes(monkeypatch):
    """Vérifie qu'une base créée avant la colonne statut la reçoit, avec l'ancien oui/non recopié.

    Sur le serveur, la base existe déjà : CREATE TABLE IF NOT EXISTS ne la modifie pas.
    """
    import sqlite3
    import uuid

    uri = f"file:ancienne_{uuid.uuid4().hex}?mode=memory&cache=shared"
    gardienne = sqlite3.connect(uri, uri=True)
    gardienne.execute(
        """
        CREATE TABLE pense_betes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            texte TEXT NOT NULL,
            integre INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    gardienne.execute("INSERT INTO pense_betes (date, texte, integre) VALUES ('d', 'Déjà intégré', 1)")
    gardienne.execute("INSERT INTO pense_betes (date, texte, integre) VALUES ('d', 'Encore en attente', 0)")
    gardienne.commit()
    monkeypatch.setattr(db, "DB_PATH", uri)

    db.initialiser()
    db.initialiser()  # une seconde fois : la migration ne se refait pas

    statuts = {pb["texte"]: pb["statut"] for pb in db.get_pense_betes()}
    assert statuts == {"Déjà intégré": db.STATUT_INTEGRE, "Encore en attente": db.STATUT_EN_ATTENTE}
    assert [pb["texte"] for pb in db.get_pense_betes(non_integres_seulement=True)] == ["Encore en attente"]
    gardienne.close()


def test_db_supprimer_note():
    """Vérifie la suppression d'une note en base SQLite et la détection d'un id inexistant."""
    id1 = db.ajouter_note("Première note")
    id2 = db.ajouter_note("Deuxième note")

    assert len(db.get_notes()) == 2

    # Suppression existante
    assert db.supprimer_note(id1) is True
    notes = db.get_notes()
    assert len(notes) == 1
    assert notes[0]["id"] == id2

    # Suppression inexistante
    assert db.supprimer_note(99999) is False

