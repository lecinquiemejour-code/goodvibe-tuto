# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Grille tarifaire et calcul des coûts estimés en USD pour GoodVibe.

Permet de convertir les tokens consommés (entrée, sortie, réflexion) et les
éventuelles images générées en estimations financières en dollars (USD).
Les tarifs sont stockés dans la base SQLite locale (table tarifs).

Aucun prix n'est écrit dans le code : c'est le pilote qui relève ceux de ses modèles sur
https://ai.google.dev/gemini-api/docs/pricing et les saisit dans l'onglet Activité.
Tant que la grille est vide, aucun coût n'est estimé : l'affichage le dit.
"""

from typing import Any, Dict, Optional

from db import get_tarifs

# Ce qui s'affiche à la place d'un coût tant que le pilote n'a pas saisi la grille de prix
TARIFS_A_RENSEIGNER = "tarifs à renseigner"


def calculer_cout_usd(
    tokens_entree: Optional[int] = 0,
    tokens_sortie: Optional[int] = 0,
    tokens_reflexion: Optional[int] = 0,
    nb_images: int = 0,
    grille_tarifs: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Calcule l'estimation du coût total en dollars USD pour une consommation donnée.

    Args:
        tokens_entree: Nombre de tokens envoyés en entrée au modèle.
        tokens_sortie: Nombre de tokens générés en réponse par le modèle.
        tokens_reflexion: Nombre de tokens de raisonnement interne.
        nb_images: Nombre d'images générées.
        grille_tarifs: Grille optionnelle passée directement (évite requêtes multiples).

    Returns:
        Montant estimé en USD, ou None si la grille de prix n'a pas été saisie :
        un coût ne se calcule pas avec des prix inventés.
    """
    tarifs = grille_tarifs or get_tarifs()
    if not tarifs:
        return None
    prix_entree = tarifs["prix_entree_usd"]
    prix_sortie = tarifs["prix_sortie_usd"]
    prix_reflexion = tarifs["prix_reflexion_usd"]
    prix_image = tarifs["prix_image_usd"]

    entree = tokens_entree or 0
    sortie = tokens_sortie or 0
    reflexion = tokens_reflexion or 0

    cout_entree = (entree / 1_000_000.0) * prix_entree
    cout_sortie = (sortie / 1_000_000.0) * prix_sortie
    cout_reflexion = (reflexion / 1_000_000.0) * prix_reflexion
    cout_images = nb_images * prix_image

    return cout_entree + cout_sortie + cout_reflexion + cout_images


def formater_cout_usd(cout_usd: Optional[float]) -> str:
    """Formate un coût en USD de manière lisible pour un humain.

    Args:
        cout_usd: Le coût calculé, ou None si la grille de prix n'a pas été saisie.

    Returns:
        Le coût mis en forme, ou « tarifs à renseigner » quand il n'a pas pu être calculé.
    """
    if cout_usd is None:
        return TARIFS_A_RENSEIGNER
    if cout_usd <= 0:
        return "-"
    elif cout_usd < 0.0001:
        return "< $0.0001"
    else:
        # Affichage avec 4 décimales en dollars (ex: $0.0192)
        return f"${cout_usd:.4f}"


# Alias de compatibilité
calculer_cout_euros = calculer_cout_usd
formater_cout_euros = formater_cout_usd
