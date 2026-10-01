# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du module de génération d'illustration (image.py).

Garanties :
- Aucun appel à Google Gemini réel (client mocké).
- Aucun fichier créé dans le vrai dossier data/images/ (dossier temporaire isolé).
- Vérification du verrou anti-doublon.
- La consigne du prompt visuel cite les éléments disponibles, et rien d'autre :
  aucune valeur par défaut pour un élément absent (Fiches 10 & 11).
- En cas de panne, un message d'erreur qui nomme la cause : ni image, ni prompt de remplacement.
"""

import base64
from pathlib import Path
from unittest.mock import MagicMock

import db
from image import generer_illustration, rediger_consigne_prompt_visuel


def test_generer_illustration_flux_nominal(monkeypatch, tmp_path):
    """Vérifie la génération d'une illustration avec client image simulé."""
    import image

    dossier_test = tmp_path / "images"
    dossier_test.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(image, "DOSSIER_IMAGES", dossier_test)

    # Mock de composition du prompt visuel
    monkeypatch.setattr(
        image,
        "composer_prompt_visuel",
        lambda **kwargs: ("A watercolor sunrise over Nantes.", "Consigne test", 30, 15),
    )

    # Mock du client Gemini pour l'image
    faux_client = MagicMock()
    fausse_reponse = MagicMock()
    faux_output = MagicMock()
    # Image PNG fictive encodée en base64
    faux_output.data = base64.b64encode(b"CONTENU_PNG_SIMULE").decode("ascii")
    fausse_reponse.output_image = faux_output
    faux_client.interactions.create.return_value = fausse_reponse

    monkeypatch.setattr(image, "get_client", lambda: faux_client)

    chemin_img, statut, coulisses, stats = generer_illustration(
        ville="Nantes",
        date_jour="2026-09-28",
        forcer=False,
    )

    assert chemin_img is not None
    assert Path(chemin_img).exists()
    assert Path(chemin_img).read_bytes() == b"CONTENU_PNG_SIMULE"
    assert stats["nb_images"] == 1
    assert db.est_deja_traite("image-2026-09-28")

    # Second appel sans forcer : l'illustration existante est rechargée sans appel au modèle
    chemin_img_2, statut_2, _, stats_2 = generer_illustration(
        ville="Nantes",
        date_jour="2026-09-28",
        forcer=False,
    )
    assert chemin_img_2 == chemin_img
    assert stats_2["deja_produite"] is True


def test_consigne_cite_la_ville_et_les_centres_d_interet():
    """Vérifie, sans appel au modèle, que les quatre éléments arrivent dans la consigne."""
    consigne = rediger_consigne_prompt_visuel(
        meteo="Lille : de 9 à 17 °C, ciel couvert.",
        ville="Lille",
        horoscope="A day of bold decisions.",
        interets="le vélo et la photographie",
    )

    assert "- City: Lille" in consigne
    assert "- Weather: Lille : de 9 à 17 °C, ciel couvert." in consigne
    assert "- Horoscope: A day of bold decisions." in consigne
    assert "- Personal interests: le vélo et la photographie" in consigne
    # Les centres d'intérêt sont un détail, pas le sujet de l'image
    assert "never the main subject" in consigne


def test_consigne_profil_vide_sans_valeur_par_defaut():
    """Vérifie qu'un profil vide n'ajoute aucune valeur par défaut à la consigne."""
    consigne = rediger_consigne_prompt_visuel(meteo="", ville="", horoscope="", interets="")

    assert "Paris" not in consigne
    assert "sunny" not in consigne.lower()
    assert "ensoleill" not in consigne.lower()
    # Aucun élément n'a de ligne dans la liste : elle dit « None »
    assert "- City:" not in consigne
    assert "- Weather:" not in consigne
    assert "- Horoscope:" not in consigne
    assert "- Personal interests:" not in consigne
    assert "### AVAILABLE ELEMENTS\n\nNone" in consigne.replace("\r\n", "\n")
    assert "do not invent any replacement" in consigne


def test_consigne_ecarte_un_element_en_erreur():
    """Vérifie qu'une source en panne n'entre pas dans la consigne : on compose avec ce qui reste."""
    consigne = rediger_consigne_prompt_visuel(
        meteo="Erreur : météo non récupérée, Open-Meteo n'a pas répondu en 5 secondes.",
        ville="Lyon",
        horoscope="Erreur : horoscope non récupéré, l'API horoscope n'a pas répondu",
        interets="",
    )

    assert "- City: Lyon" in consigne
    assert "Erreur" not in consigne
    assert "- Weather:" not in consigne
    assert "- Horoscope:" not in consigne


def test_consigne_vient_du_fichier_prompt_image(monkeypatch, tmp_path):
    """Vérifie que la consigne se lit dans prompt_image.md : on change le style sans toucher au code."""
    import image

    fichier = tmp_path / "prompt_image.md"
    fichier.write_text("Style aquarelle.\n{elements}\nFin.", encoding="utf-8")
    monkeypatch.setattr(image, "PROMPT_IMAGE_PATH", fichier)

    consigne = rediger_consigne_prompt_visuel(ville="Lille")

    assert consigne == "Style aquarelle.\n- City: Lille\nFin."


def test_prompt_image_absent_rend_un_message_d_erreur(monkeypatch, tmp_path):
    """Vérifie qu'aucune consigne de secours n'existe dans le code : fichier absent, message d'erreur."""
    import image

    monkeypatch.setattr(image, "PROMPT_IMAGE_PATH", tmp_path / "prompt_image.md")
    faux_client = MagicMock()
    monkeypatch.setattr(image, "get_client", lambda: faux_client)

    chemin_img, statut, _, stats = generer_illustration(ville="Lyon", date_jour="2026-09-29")

    assert chemin_img is None
    assert "impossible de composer le prompt visuel" in statut
    assert "prompt_image.md est introuvable" in statut
    # Aucun modèle n'a été appelé
    assert faux_client.interactions.create.call_count == 0


def test_prompt_image_sans_marqueur_rend_un_message_d_erreur(monkeypatch, tmp_path):
    """Vérifie qu'un fichier sans marqueur {elements} est signalé, au lieu d'une image sans éléments."""
    import image

    fichier = tmp_path / "prompt_image.md"
    fichier.write_text("Une consigne sans marqueur.", encoding="utf-8")
    monkeypatch.setattr(image, "PROMPT_IMAGE_PATH", fichier)
    monkeypatch.setattr(image, "get_client", lambda: MagicMock())

    chemin_img, statut, _, _ = generer_illustration(ville="Lyon", date_jour="2026-09-29")

    assert chemin_img is None
    assert "le marqueur {elements} manque" in statut


def test_prompt_image_sans_donnee_personnelle():
    """Vérifie que prompt_image.md, enregistré dans le dépôt, ne contient que le texte fixe et son marqueur."""
    from config import PROMPT_IMAGE_PATH

    texte = PROMPT_IMAGE_PATH.read_text(encoding="utf-8")
    assert texte.count("{elements}") == 1
    assert "never the main subject" in texte


def test_prompt_visuel_vide_rend_un_message_d_erreur(monkeypatch):
    """Vérifie qu'un prompt visuel vide n'est remplacé par aucun prompt écrit d'avance."""
    import image

    # Le modèle texte répond, mais sa réponse est vide
    faux_client = MagicMock()
    faux_client.interactions.create.return_value = MagicMock(output_text="   ")
    monkeypatch.setattr(image, "get_client", lambda: faux_client)

    chemin_img, statut, coulisses, stats = generer_illustration(
        ville="Lyon",
        date_jour="2026-09-29",
        forcer=False,
    )

    assert chemin_img is None
    assert statut.startswith("Erreur : illustration non générée, impossible de composer le prompt visuel")
    assert "prompt visuel vide" in statut
    assert stats["nb_images"] == 0
    # Le modèle image n'a pas été appelé : un seul appel, celui du modèle texte
    assert faux_client.interactions.create.call_count == 1
    assert not db.est_deja_traite("image-2026-09-29")


def test_panne_du_modele_image_rend_un_message_d_erreur(monkeypatch, tmp_path):
    """Vérifie qu'une panne du modèle image rend un message d'erreur qui nomme la cause."""
    import image

    dossier_test = tmp_path / "images"
    dossier_test.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(image, "DOSSIER_IMAGES", dossier_test)
    monkeypatch.setattr(
        image,
        "composer_prompt_visuel",
        lambda **kwargs: ("A watercolor sunrise over Nantes.", "Consigne test", 30, 15),
    )

    # Simuler une panne du modèle image (ex: quota dépassé)
    faux_client = MagicMock()
    faux_client.interactions.create.side_effect = RuntimeError("Quota image épuisé")
    monkeypatch.setattr(image, "get_client", lambda: faux_client)

    chemin_img, statut, coulisses, stats = generer_illustration(
        ville="Nantes",
        date_jour="2026-09-29",
        forcer=False,
    )

    # Aucun blocage, aucune image de remplacement : None et un message qui dit la cause
    assert chemin_img is None
    assert "illustration non générée" in statut
    assert "Quota image épuisé" in statut
    assert stats["nb_images"] == 0
    assert list(dossier_test.iterdir()) == []


def test_prompt_visuel_absent_du_journal_et_des_logs(monkeypatch, caplog):
    """Vérifie que le prompt visuel, qui cite la ville et les centres d'intérêt, n'est enregistré nulle part.

    Le journal note seulement que le prompt a été composé, avec ses tokens.
    """
    import logging

    import image
    from journal import get_dernieres_activites

    faux_client = MagicMock()
    fausse_reponse = MagicMock(output_text="A morning view of Lille with a parked bicycle.")
    fausse_reponse.usage.input_tokens = 120
    fausse_reponse.usage.output_tokens = 30
    faux_client.interactions.create.return_value = fausse_reponse
    monkeypatch.setattr(image, "get_client", lambda: faux_client)

    with caplog.at_level(logging.INFO):
        prompt, consigne, entree, sortie = image.composer_prompt_visuel(ville="Lille", interets="le vélo")

    # Le prompt est bien rendu à l'appelant, qui l'affiche dans les coulisses...
    assert prompt == "A morning view of Lille with a parked bicycle."

    # ... mais ni le journal ni les logs n'en gardent le texte
    lignes = [a for a in get_dernieres_activites() if a["etape"] == "image_prompt"]
    assert len(lignes) == 1
    assert lignes[0]["detail"] == "Prompt visuel composé"
    assert lignes[0]["tokens_entree"] == 120
    assert "Lille" not in caplog.text
    assert "bicycle" not in caplog.text


def test_echec_de_regeneration_retire_l_image_du_jour(monkeypatch, tmp_path):
    """Vérifie qu'une régénération en échec retire l'image produite plus tôt dans la journée.

    L'image du jour est celle du dernier brief, ou il n'y en a pas : elle ne doit pas
    revenir au rechargement de la page à côté d'un brief qui annonce une erreur.
    """
    import image

    dossier_test = tmp_path / "images"
    dossier_test.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(image, "DOSSIER_IMAGES", dossier_test)
    monkeypatch.setattr(
        image,
        "composer_prompt_visuel",
        lambda **kwargs: ("A watercolor sunrise over Nantes.", "Consigne test", 30, 15),
    )

    # Une image du jour existe déjà, produite par un brief précédent
    ancienne = dossier_test / "2026-09-30.png"
    ancienne.write_bytes(b"IMAGE_DU_MATIN")
    db.marquer_traite("image-2026-09-30")

    # La régénération forcée tombe sur une panne du modèle image
    faux_client = MagicMock()
    faux_client.interactions.create.side_effect = RuntimeError("Quota image épuisé")
    monkeypatch.setattr(image, "get_client", lambda: faux_client)

    chemin_img, statut, _, _ = generer_illustration(ville="Nantes", date_jour="2026-09-30", forcer=True)

    assert chemin_img is None
    assert "illustration non générée" in statut
    assert not ancienne.exists()
    assert image.get_image_du_jour("2026-09-30") is None
