# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Confirmation des suppressions par l'utilisateur (Features 5 et 14).

Une consigne donnée au modèle est une demande ; une règle codée ici est une garantie.
Le modèle peut proposer une suppression (une note, un pense-bête, ou tout), jamais
l'exécuter : l'outil dépose une demande en attente, l'interface l'affiche, et seul un
geste de l'utilisateur (le bouton de la page, la question posée au terminal) déclenche
la suppression. Quoi que le modèle demande, rien n'est supprimé sans ce geste.

Une seule demande à la fois : une nouvelle proposition remplace la précédente, et la
confirmation ne vaut que pour l'élément affiché. Après exécution ou refus, il ne reste
rien à confirmer : un second clic ne supprime rien.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import db
from journal import consigner_activite
from oubli import effacer_utilisateur

logger = logging.getLogger("goodvibe.confirmation")

# Les trois suppressions que GoodVibe sait proposer
NOTE = "note"
PENSE_BETE = "pense_bete"
TOUT = "tout"

RIEN_EN_ATTENTE = "Aucune suppression en attente."
RIEN_SUPPRIME = "Rien n'a été supprimé."


@dataclass(frozen=True)
class Demande:
    """Une suppression proposée par le modèle, qui attend le geste de l'utilisateur.

    Attributes:
        type: NOTE, PENSE_BETE ou TOUT.
        id: L'identifiant de l'élément visé (None pour TOUT).
        libelle: Ce que l'utilisateur voit avant de confirmer, par exemple
            « Note n° 2, « Dentiste mardi à 10 h » ». C'est sur ce libellé qu'il décide.
    """

    type: str
    id: Optional[int]
    libelle: str


# La demande en attente, pour le processus en cours (la page ou le terminal).
# Elle n'a de sens que pendant l'échange : inutile de la ranger en base.
_demande_en_attente: Optional[Demande] = None


def proposer(type_: str, id_: Optional[int], libelle: str) -> Demande:
    """Dépose une demande de suppression, en remplaçant celle qui attendait encore.

    Args:
        type_: NOTE, PENSE_BETE ou TOUT.
        id_: L'identifiant de l'élément visé, ou None pour TOUT.
        libelle: Le texte affiché à l'utilisateur avant qu'il confirme.

    Returns:
        La demande déposée.
    """
    global _demande_en_attente
    if _demande_en_attente is not None:
        logger.info("[CONFIRMATION] Demande précédente remplacée (%s)", _demande_en_attente.type)
    _demande_en_attente = Demande(type=type_, id=id_, libelle=libelle)
    # Journal sans le libellé : il contient le texte de la note ou du pense-bête
    consigner_activite("confirmation", f"suppression proposée ({type_}), en attente de confirmation")
    logger.info("[CONFIRMATION] Demande en attente : %s", type_)
    return _demande_en_attente


def en_attente() -> Optional[Demande]:
    """Rend la demande qui attend une confirmation, ou None."""
    return _demande_en_attente


def question(demande: Demande) -> str:
    """Rédige la question posée à l'utilisateur pour une demande.

    Args:
        demande: La demande en attente.

    Returns:
        La question, par exemple « Supprimer la note n° 2, « Dentiste mardi à 10 h » ? ».
    """
    if demande.type == TOUT:
        return f"Effacer {demande.libelle} ?"
    return f"Supprimer {demande.libelle} ?"


def refuser() -> str:
    """Abandonne la demande en attente, s'il y en a une. Rien n'est supprimé.

    Returns:
        Le message à afficher à l'utilisateur.
    """
    global _demande_en_attente
    if _demande_en_attente is None:
        return RIEN_EN_ATTENTE
    consigner_activite("confirmation", f"suppression refusée ({_demande_en_attente.type})")
    logger.info("[CONFIRMATION] Demande refusée : %s", _demande_en_attente.type)
    _demande_en_attente = None
    return RIEN_SUPPRIME


def ligne_issue(message: str, annulation: bool = False) -> str:
    """Rédige la ligne inscrite dans la conversation après le geste de l'utilisateur.

    C'est le programme qui écrit cette ligne, pas le modèle. Au message suivant, le
    modèle la relit et sait que sa proposition n'attend plus : sans elle, il croit la
    demande toujours en attente et ne la repropose pas quand l'utilisateur redemande.

    Args:
        message: Le message rendu par confirmer() ou refuser().
        annulation: True si l'utilisateur a refusé.

    Returns:
        La ligne à ajouter à la conversation, la même dans la page et dans le terminal.
    """
    if annulation:
        return f"❌ Suppression annulée. {message}"
    # Une confirmation peut ne rien supprimer (élément déjà parti) : la marque le dit
    marque = "❌" if RIEN_SUPPRIME in message else "✅"
    return f"{marque} {message}"


def confirmer() -> str:
    """Exécute la demande en attente, et elle seule, puis l'efface.

    C'est le seul endroit du programme où une suppression demandée par le modèle
    s'exécute. L'élément supprimé est celui que la demande désigne : celui qui a été
    affiché à l'utilisateur, pas un autre.

    Returns:
        Le message à afficher à l'utilisateur.
    """
    global _demande_en_attente
    demande = _demande_en_attente
    if demande is None:
        logger.info("[CONFIRMATION] Confirmation reçue sans demande en attente : rien à faire")
        return RIEN_EN_ATTENTE
    # La demande est consommée avant d'agir : un second clic ne trouvera rien
    _demande_en_attente = None

    if demande.type == NOTE:
        succes = db.supprimer_note(demande.id)
        # Journal sans le texte de la note
        consigner_activite("confirmation", "note retirée" if succes else "note introuvable au moment de la confirmation")
        logger.info("[CONFIRMATION] Note %s : %s", demande.id, "retirée" if succes else "introuvable")
        if succes:
            return f"Note n° {demande.id} retirée."
        return f"Aucune note trouvée avec l'identifiant {demande.id}. {RIEN_SUPPRIME}"

    if demande.type == PENSE_BETE:
        succes = db.supprimer_pense_bete(demande.id)
        consigner_activite(
            "confirmation",
            "pense-bête retiré" if succes else "pense-bête introuvable au moment de la confirmation",
        )
        logger.info("[CONFIRMATION] Pense-bête %s : %s", demande.id, "retiré" if succes else "introuvable")
        if succes:
            return f"Pense-bête n° {demande.id} retiré."
        return f"Aucun pense-bête trouvé avec l'identifiant {demande.id}. {RIEN_SUPPRIME}"

    # TOUT : le même effacement que le bouton « Oublie-moi » de l'onglet Mémoire
    consigner_activite("confirmation", "effacement confirmé")
    logger.info("[CONFIRMATION] Effacement complet confirmé par l'utilisateur")
    return effacer_utilisateur()
