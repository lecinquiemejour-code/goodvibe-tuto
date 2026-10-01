# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires des outils autonomes de GoodVibe (Feature 4 & 11).

Vérifie :
- Le calcul du signe astrologique occidental sans conservation de la date de naissance.
- L'enregistrement et la lecture du profil utilisateur.
- L'enregistrement et la lecture des notes/pense-bêtes.
- L'action irréversible d'oubli des données privées.
"""

import pytest

import db
from outils import (
    ecrire_note,
    enregistrer_profil,
    executer_outil,
    lire_notes,
    oublier_utilisateur,
    signe_depuis_date,
    supprimer_note,
)

# ============================================================================
# 1. TESTS DU CALCUL DU SIGNE ASTROLOGIQUE (signe_depuis_date)
# ============================================================================

@pytest.mark.parametrize(
    "jour, mois, signe_attendu",
    [
        (21, 3, "Bélier"),
        (19, 4, "Bélier"),
        (20, 4, "Taureau"),
        (20, 5, "Taureau"),
        (21, 5, "Gémeaux"),
        (20, 6, "Gémeaux"),
        (21, 6, "Cancer"),
        (22, 7, "Cancer"),
        (23, 7, "Lion"),
        (22, 8, "Lion"),
        (23, 8, "Vierge"),
        (22, 9, "Vierge"),
        (23, 9, "Balance"),
        (22, 10, "Balance"),
        (23, 10, "Scorpion"),
        (21, 11, "Scorpion"),
        (22, 11, "Sagittaire"),
        (21, 12, "Sagittaire"),
        (22, 12, "Capricorne"),
        (19, 1, "Capricorne"),
        (20, 1, "Verseau"),
        (18, 2, "Verseau"),
        (19, 2, "Poissons"),
        (20, 3, "Poissons"),
    ],
)
def test_signe_depuis_date_tous_signes(jour: int, mois: int, signe_attendu: str):
    """Vérifie que chaque date clé est associée au bon signe zodiacal."""
    assert signe_depuis_date(jour, mois) == signe_attendu


def test_signe_depuis_date_inconnu():
    """Vérifie le comportement en cas de mois invalide."""
    assert signe_depuis_date(10, 13) == "Inconnu"
    assert signe_depuis_date(10, 0) == "Inconnu"


# ============================================================================
# 2. TESTS DE GESTION DU PROFIL ET DES NOTES
# ============================================================================

def test_enregistrer_et_consulter_profil():
    """Vérifie l'enregistrement autonome du profil et le calcul du signe."""
    retour = enregistrer_profil(
        prenom="Alice",
        ville="Lyon",
        interets="piano et jardinage",
        jour_naissance=15,
        mois_naissance=5,
    )
    assert "Alice" in retour
    assert "Lyon" in retour
    assert "Taureau" in retour

    profil = db.get_profil()
    assert profil is not None
    assert profil["prenom"] == "Alice"
    assert profil["ville"] == "Lyon"
    assert profil["signe"] == "Taureau"
    assert profil["interets"] == "piano et jardinage"


def test_ajouter_et_consulter_notes():
    """Vérifie l'enregistrement et la récupération de notes personnelles via les outils."""
    res1 = ecrire_note("Acheter du pain")
    res2 = ecrire_note("Rendez-vous dentiste jeudi 14h")

    assert "enregistrée" in res1
    assert "enregistrée" in res2

    notes_db = db.get_notes(limite=5)
    assert len(notes_db) == 2
    # Tri décroissant par id
    assert notes_db[0]["texte"] == "Rendez-vous dentiste jeudi 14h"
    assert notes_db[1]["texte"] == "Acheter du pain"

    notes_outil = lire_notes()
    assert len(notes_outil) == 2
    textes = [n["texte"] for n in notes_outil]
    assert "Acheter du pain" in textes
    assert "Rendez-vous dentiste jeudi 14h" in textes


def test_oublier_utilisateur():
    """Vérifie que l'action d'oubli efface profil, notes et conversations sans toucher au journal."""
    # Préparation des données
    enregistrer_profil(prenom="Bob", ville="Marseille")
    ecrire_note("Note secrète")
    db.sauvegarder_message("user", "Mon message privé")

    # Vérification présence
    assert db.get_profil() is not None
    assert len(db.get_notes()) == 1
    assert len(db.charger_historique()) == 1

    # Action d'effacement
    res = oublier_utilisateur()
    assert "définitivement effacées" in res

    # Vérification de l'amnésie complète
    assert db.get_profil() is None
    assert len(db.get_notes()) == 0
    assert len(db.charger_historique()) == 0


def test_supprimer_note_existant_et_inexistant():
    """Vérifie la suppression ciblée d'une note et la gestion d'un identifiant inexistant."""
    db.ajouter_note("Note 1")
    id2 = db.ajouter_note("Note 2")
    db.ajouter_note("Note 3")

    notes = db.get_notes()
    assert len(notes) == 3

    # Suppression réussie
    res_succes = supprimer_note(id_note=id2)
    assert "supprimée avec succès" in res_succes
    notes_apres = db.get_notes()
    assert len(notes_apres) == 2
    assert id2 not in [n["id"] for n in notes_apres]

    # Suppression d'un ID qui n'existe pas
    res_inexistant = supprimer_note(id_note=9999)
    assert "Aucune note trouvée" in res_inexistant
    assert len(db.get_notes()) == 2


def test_executer_outil_supprimer_note():
    """Vérifie que le routeur d'outils appelle bien supprimer_note."""
    id_note = db.ajouter_note("À supprimer via executer_outil")
    res = executer_outil("supprimer_note", {"id_note": id_note})
    assert "supprimée avec succès" in res
    assert len(db.get_notes()) == 0


def test_lire_notes_rend_toutes_les_notes_avec_identifiant():
    """Vérifie que lire_notes retourne l'ensemble des notes (au-delà de 10) avec leur identifiant."""
    # Création de 12 notes pour dépasser l'ancienne limite de 10
    ids_crees = []
    for i in range(1, 13):
        note_id = db.ajouter_note(f"Note test numéro {i}")
        ids_crees.append(note_id)

    notes = lire_notes()
    # Toutes les notes doivent être présentes
    assert len(notes) == 12
    # Chaque note doit contenir son identifiant numérique unique et son texte
    for note in notes:
        assert "id" in note
        assert "texte" in note
        assert note["id"] in ids_crees
        assert f"Note test numéro {note['id']}" in note["texte"]

