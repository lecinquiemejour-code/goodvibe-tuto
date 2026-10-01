# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""L'effacement complet de l'utilisateur, « Oublie-moi » (Features 5, 9 et 14).

Un seul endroit connaît le périmètre réel de l'effacement : la base (profil, notes,
conversations, pense-bêtes, briefs, verrous du jour) et le disque (les images du jour).
Les deux chemins qui effacent, le bouton de l'onglet Mémoire et la confirmation d'une
demande faite dans le chat, passent par ici : aucun des deux ne peut oublier une partie.

Ce que l'effacement ne couvre pas, et que le message dit : les sauvegardes nocturnes du
serveur, qui gardent une copie de la base jusqu'à leur expiration (deploy/sauvegarde.sh
les supprime au bout de 7 jours), et ce que Google conserve des échanges déjà transmis
à Gemini, selon ses propres règles.
"""

import logging

import db
from image import supprimer_toutes_les_images
from journal import consigner_activite

logger = logging.getLogger("goodvibe.oubli")

# Le message affiché après l'effacement, le même partout : il annonce exactement le périmètre
MESSAGE_EFFACEMENT = (
    "Ton profil, tes notes, tes conversations, tes pense-bêtes et tes briefs sont effacés de "
    "GoodVibe. Les sauvegardes du serveur en gardent une copie jusqu'à leur expiration. "
    "Les échanges déjà transmis à Gemini dépendent des règles de conservation de Google."
)

# L'avertissement affiché avant le geste de l'utilisateur : le même périmètre, au futur
AVERTISSEMENT_EFFACEMENT = (
    "Cette action est irréversible. Elle effacera ton profil, tes notes, tes conversations, "
    "tes pense-bêtes, tes briefs et les images du jour. Le journal d'activité (tokens, durées) "
    "est conservé : il ne contient aucune donnée personnelle. Les sauvegardes du serveur "
    "gardent une copie jusqu'à leur expiration, et ce que Google conserve des échanges déjà "
    "transmis à Gemini dépend de ses règles."
)


def effacer_utilisateur() -> str:
    """Efface tout ce que GoodVibe sait de l'utilisateur, en base et sur le disque.

    Appelée uniquement sur un geste de l'utilisateur : jamais par le modèle.

    Returns:
        Le message à afficher, qui annonce le périmètre réel de l'effacement.
    """
    logger.info("[OUBLI] Effacement complet demandé par l'utilisateur")
    db.effacer_donnees_utilisateur()
    nb_images = supprimer_toutes_les_images()
    # Journal sans donnée personnelle : le fait, et le nombre d'images retirées
    consigner_activite("oubli", f"profil effacé, briefs effacés, {nb_images} image(s) retirée(s)")
    logger.info("[OUBLI] Effacement terminé")
    return MESSAGE_EFFACEMENT
