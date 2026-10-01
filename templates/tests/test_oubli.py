# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests de l'effacement complet « Oublie-moi » (oubli.py, Features 5, 9 et 14).

Garanties :
- Après l'effacement, aucun brief n'est récupérable, ni en base ni dans la page.
- Les images du jour sont retirées du disque, et les verrous du jour de la table traites.
- Le journal et la grille de prix restent : ils ne contiennent aucune donnée personnelle.
- Le message affiché est celui qui annonce le périmètre réel, sur les deux chemins.
"""

import confirmation
import db
import image
import journal
import outils
from interface import MESSAGE_SANS_BRIEF, charger_page
from oubli import MESSAGE_EFFACEMENT, effacer_utilisateur


def preparer_un_utilisateur_complet():
    """Remplit tout ce que GoodVibe peut savoir d'un utilisateur, données dérivées comprises."""
    db.sauvegarder_profil(prenom="Zoe", ville="Lille", signe="Lion", interets="le vélo")
    db.ajouter_note("Dentiste mardi à 10 h")
    db.sauvegarder_message("user", "Je m'appelle Zoe")
    db.ajouter_pense_bete("Rappeler le plombier")
    db.sauvegarder_brief(contenu="Bonjour Zoe, belle journée à Lille.", date_jour="2026-10-01")
    db.marquer_traite("brief:2026-10-01")
    db.marquer_traite("image-2026-10-01")
    db.sauvegarder_tarifs(prix_entree_usd=1.0, prix_sortie_usd=2.0, prix_reflexion_usd=2.0, prix_image_usd=0.05)
    image.DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
    (image.DOSSIER_IMAGES / "2026-10-01.png").write_bytes(b"IMAGE")
    (image.DOSSIER_IMAGES / "2026-09-30.png").write_bytes(b"IMAGE")


def test_aucun_brief_recuperable_apres_effacement():
    """Les briefs partent avec le profil : ni en base, ni dans la page, ni par le dernier brief."""
    preparer_un_utilisateur_complet()
    assert db.get_dernier_brief() is not None

    message = effacer_utilisateur()

    assert message == MESSAGE_EFFACEMENT
    assert db.get_dernier_brief() is None
    assert charger_page()[4] == MESSAGE_SANS_BRIEF
    assert db.get_connection().execute("SELECT COUNT(*) FROM briefs").fetchone()[0] == 0


def test_images_et_verrous_du_jour_retires():
    """Les images du jour et les verrous anti-doublon des briefs disparaissent aussi."""
    preparer_un_utilisateur_complet()
    db.marquer_traite("autre:cle")

    effacer_utilisateur()

    assert list(image.DOSSIER_IMAGES.iterdir()) == []
    assert image.get_image_du_jour("2026-10-01") is None
    assert not db.est_deja_traite("brief:2026-10-01")
    assert not db.est_deja_traite("image-2026-10-01")
    # Seuls les verrous des briefs et des images sont visés
    assert db.est_deja_traite("autre:cle")


def test_tables_personnelles_vides_journal_et_tarifs_intacts():
    """Les quatre tables de l'utilisateur se vident ; le journal et la grille de prix restent."""
    preparer_un_utilisateur_complet()

    effacer_utilisateur()

    assert db.get_profil() is None
    assert db.get_notes() == []
    assert db.charger_historique() == []
    assert db.get_pense_betes() == []
    assert db.get_tarifs() is not None
    lignes = [e for e in journal.get_dernieres_activites() if e["etape"] == "oubli"]
    assert len(lignes) == 1
    assert lignes[0]["detail"] == "profil effacé, briefs effacés, 2 image(s) retirée(s)"
    assert "Zoe" not in lignes[0]["detail"]


def test_effacement_sans_dossier_images():
    """Un dossier d'images absent n'empêche pas l'effacement."""
    db.sauvegarder_profil(prenom="Zoe")
    if image.DOSSIER_IMAGES.exists():
        image.DOSSIER_IMAGES.rmdir()

    assert effacer_utilisateur() == MESSAGE_EFFACEMENT
    assert db.get_profil() is None


def test_le_chemin_du_chat_fait_le_meme_effacement():
    """L'effacement confirmé depuis le chat passe par oubli.py : briefs et images compris."""
    preparer_un_utilisateur_complet()
    outils.oublier_utilisateur()

    message = confirmation.confirmer()

    assert message == MESSAGE_EFFACEMENT
    assert db.get_dernier_brief() is None
    assert list(image.DOSSIER_IMAGES.iterdir()) == []
    assert db.get_profil() is None
