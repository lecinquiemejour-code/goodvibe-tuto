# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Fragments émis par la boucle d'agent de GoodVibe.

Sépare à la source ce qu'on montre de ce qu'on retient : chaque fragment dit sa
nature. L'écran affiche tout ; l'historique et la base ne gardent que le texte des
fragments de réponse. Aucun code ne retrouve les coulisses en cherchant des
libellés dans un texte affiché.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Iterable, List, Tuple

# Les quatre natures possibles d'un fragment
COULISSES = "coulisses"  # réflexion, appels d'outils, requêtes : pour les yeux seulement
REPONSE = "reponse"  # le propos de GoodVibe : seul texte retenu
RELEVE = "releve"  # le décompte de fin : pour les yeux seulement
FLUX = "flux"  # un événement brut reçu de Gemini : pour les yeux seulement, dans son panneau


@dataclass(frozen=True)
class Fragment:
    """Un morceau de ce que la boucle d'agent produit.

    Attributes:
        nature: COULISSES, REPONSE, RELEVE ou FLUX.
        texte: Le contenu à afficher (Markdown).
        titre: Le titre du bloc, pour les coulisses.
        replie: Si True, le bloc de coulisses s'affiche replié.
        chiffres: Pour le relevé, les valeurs comptées (tokens, tours, durées) :
            qui en a besoin les lit ici, jamais dans le texte affiché.
        outil: Pour les coulisses d'un appel d'outil, le nom de l'outil appelé.
        resultat: Pour les coulisses d'un appel d'outil, le résultat rendu au modèle :
            qui en a besoin (le brief, pour l'image) le lit ici, jamais dans le texte affiché.
        evenement: Pour le flux, l'événement reçu de Gemini, tel quel, en dictionnaire.
        tour: Pour le flux, le numéro du tour pendant lequel l'événement est arrivé.
    """

    nature: str
    texte: str = ""
    titre: str = ""
    replie: bool = False
    chiffres: Dict[str, int] = field(default_factory=dict)
    outil: str = ""
    resultat: Any = None
    evenement: Any = None
    tour: int = 0


def en_markdown(fragment: Fragment) -> str:
    """Met en forme un fragment pour un affichage en texte (terminal, zone du brief).

    Args:
        fragment: Le fragment à afficher.

    Returns:
        Le texte Markdown correspondant.
    """
    if fragment.nature == REPONSE:
        return fragment.texte
    if fragment.nature == RELEVE:
        return f"\n\n---\n*{fragment.texte}*"
    if fragment.nature == FLUX:
        # Le flux brut ne s'écrit pas dans le fil : il a son propre panneau dans la page
        return ""
    if fragment.replie:
        return (
            f"<details style='margin-top: 18px; margin-bottom: 12px;'>\n"
            f"<summary style='cursor: pointer;'><b>{fragment.titre}</b> "
            f"<i>(cliquer pour déplier)</i></summary>\n\n"
            f"{fragment.texte}\n\n"
            f"</details>\n\n"
        )
    return f"\n> **{fragment.titre}**\n{fragment.texte}\n\n"


def avec_markdown(
    fragments: Iterable[Fragment],
) -> Generator[Tuple[Fragment, str], None, None]:
    """Accompagne chaque fragment de son texte à afficher.

    Ajoute l'en-tête « Réponse de GoodVibe » quand la réponse suit des coulisses :
    c'est un repère pour l'œil, qui n'appartient ni à la réponse ni à l'historique.

    Args:
        fragments: Le flux de fragments rendu par la boucle d'agent.

    Yields:
        Des couples (fragment, texte à afficher).
    """
    coulisses_vues = False
    en_tete_emis = False
    for fragment in fragments:
        texte = en_markdown(fragment)
        if fragment.nature == COULISSES:
            coulisses_vues = True
        elif fragment.nature == REPONSE and coulisses_vues and not en_tete_emis:
            texte = "\n> ☀️ **Réponse de GoodVibe :**\n\n" + texte
            en_tete_emis = True
        yield fragment, texte


def ajouter_au_flux(flux_recu: Dict[str, List[Any]], fragment: Fragment) -> None:
    """Range l'événement d'un fragment de flux sous son tour.

    Le chat et le brief tiennent chacun leur flux de cette façon, pour l'envoyer
    à leur panneau : {"Tour 1": [événement, événement...], "Tour 2": [...]}.

    Args:
        flux_recu: Les événements bruts déjà reçus, rangés par tour. Modifié sur place.
        fragment: Un fragment de nature FLUX.
    """
    flux_recu.setdefault(f"Tour {fragment.tour}", []).append(fragment.evenement)


def copier_flux(flux_recu: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
    """Rend une copie du flux reçu, pour l'envoyer au panneau.

    Chaque envoi à la page reçoit sa propre copie : l'objet qu'on continue de
    remplir ne part jamais tel quel.

    Args:
        flux_recu: Les événements bruts reçus de Gemini, rangés par tour.

    Returns:
        Le même contenu, dans un nouveau dictionnaire et de nouvelles listes.
    """
    return {tour: list(evenements) for tour, evenements in flux_recu.items()}
