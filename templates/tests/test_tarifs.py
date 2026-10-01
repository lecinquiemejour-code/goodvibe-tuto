# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Tests unitaires du calcul des coûts et tarifs en USD (tarifs.py).

Garanties :
- Le coût se calcule avec la grille saisie par le pilote, et avec elle seule.
- Aucun prix n'est écrit dans le code : sans grille, aucun coût n'est estimé, et l'affichage le dit.

Les prix de ces tests sont des nombres ronds choisis pour le calcul : ce ne sont pas ceux d'un modèle.
"""

import db
from tarifs import TARIFS_A_RENSEIGNER, calculer_cout_usd, formater_cout_usd

GRILLE_DE_TEST = {
    "prix_entree_usd": 1.0,
    "prix_sortie_usd": 2.0,
    "prix_reflexion_usd": 2.0,
    "prix_image_usd": 0.05,
}


def test_calculer_cout_usd_tokens_seuls():
    """Vérifie le calcul avec 1 million de tokens d'entrée et de sortie."""
    # 1M entrée = 1.00 $, 1M sortie = 2.00 $, 500k réflexion = 1.00 $
    cout = calculer_cout_usd(
        tokens_entree=1_000_000,
        tokens_sortie=1_000_000,
        tokens_reflexion=500_000,
        nb_images=0,
        grille_tarifs=GRILLE_DE_TEST,
    )
    assert round(cout, 4) == 4.0000


def test_calculer_cout_avec_image():
    """Vérifie le surcoût de la génération d'image, au prix de la grille."""
    cout_sans_image = calculer_cout_usd(
        tokens_entree=10_000, tokens_sortie=1_000, nb_images=0, grille_tarifs=GRILLE_DE_TEST
    )
    cout_avec_image = calculer_cout_usd(
        tokens_entree=10_000, tokens_sortie=1_000, nb_images=1, grille_tarifs=GRILLE_DE_TEST
    )

    difference = cout_avec_image - cout_sans_image
    assert round(difference, 4) == 0.0500


def test_calculer_cout_lit_la_grille_saisie_en_base():
    """Vérifie que, sans grille passée en argument, le calcul lit celle que le pilote a enregistrée."""
    db.sauvegarder_tarifs(
        prix_entree_usd=1.0, prix_sortie_usd=2.0, prix_reflexion_usd=2.0, prix_image_usd=0.05
    )

    assert round(calculer_cout_usd(tokens_entree=1_000_000), 4) == 1.0000
    assert round(calculer_cout_usd(nb_images=2), 4) == 0.1000


def test_sans_grille_aucun_cout_n_est_estime():
    """Vérifie qu'une base neuve n'a aucun prix : le coût n'est pas calculé, et l'affichage le dit."""
    assert db.get_tarifs() is None

    cout = calculer_cout_usd(tokens_entree=1_000_000, tokens_sortie=1_000_000, nb_images=1)

    assert cout is None
    assert formater_cout_usd(cout) == TARIFS_A_RENSEIGNER


def test_formater_cout_usd():
    """Vérifie les différents formats d'affichage du coût."""
    assert formater_cout_usd(0.0) == "-"
    assert formater_cout_usd(0.00005) == "< $0.0001"
    assert formater_cout_usd(0.01234) == "$0.0123"
