# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Boîte à outils de GoodVibe (Feature 4).

Fournit les premiers outils autonomes de l'agent : gestion du profil utilisateur
(avec calcul du signe astrologique en Python pur sans stocker la date de naissance),
lecture et écriture de notes, ainsi que les spécifications transmises à Gemini.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

import db
from horoscope import ERREUR_SERVEUR_FETCH, lire_horoscope_du_profil
from journal import consigner_activite, lire_journal_execution
from mcp_client import ServeurMCPNonDemarre, lister_outils_mcp
from outils_meteo import obtenir_meteo
from tarifs import calculer_cout_usd, formater_cout_usd


def signe_depuis_date(jour: int, mois: int) -> str:
    """Calcule le signe astrologique occidental à partir du jour et du mois.

    Règle de minimisation : calculé directement en Python sans jamais conserver
    la date de naissance complète dans la base de données.
    """
    if (mois == 3 and jour >= 21) or (mois == 4 and jour <= 19):
        return "Bélier"
    elif (mois == 4 and jour >= 20) or (mois == 5 and jour <= 20):
        return "Taureau"
    elif (mois == 5 and jour >= 21) or (mois == 6 and jour <= 20):
        return "Gémeaux"
    elif (mois == 6 and jour >= 21) or (mois == 7 and jour <= 22):
        return "Cancer"
    elif (mois == 7 and jour >= 23) or (mois == 8 and jour <= 22):
        return "Lion"
    elif (mois == 8 and jour >= 23) or (mois == 9 and jour <= 22):
        return "Vierge"
    elif (mois == 9 and jour >= 23) or (mois == 10 and jour <= 22):
        return "Balance"
    elif (mois == 10 and jour >= 23) or (mois == 11 and jour <= 21):
        return "Scorpion"
    elif (mois == 11 and jour >= 22) or (mois == 12 and jour <= 21):
        return "Sagittaire"
    elif (mois == 12 and jour >= 22) or (mois == 1 and jour <= 19):
        return "Capricorne"
    elif (mois == 1 and jour >= 20) or (mois == 2 and jour <= 18):
        return "Verseau"
    elif (mois == 2 and jour >= 19) or (mois == 3 and jour <= 20):
        return "Poissons"
    return "Inconnu"


def enregistrer_profil(
    prenom: Optional[str] = None,
    ville: Optional[str] = None,
    interets: Optional[str] = None,
    jour_naissance: Optional[int] = None,
    mois_naissance: Optional[int] = None,
) -> str:
    """Enregistre ou met à jour les informations du profil utilisateur."""
    t0 = time.time()
    signe = None
    if jour_naissance is not None and mois_naissance is not None:
        try:
            signe = signe_depuis_date(int(jour_naissance), int(mois_naissance))
        except (ValueError, TypeError):
            signe = None

    db.sauvegarder_profil(prenom=prenom, ville=ville, interets=interets, signe=signe)
    duree_ms = int((time.time() - t0) * 1000)

    # Journalisation technique sans argument personnel
    consigner_activite(
        etape="outil:enregistrer_profil",
        detail="Mise à jour du profil utilisateur",
        duree_ms=duree_ms,
    )

    details = []
    if prenom:
        details.append(f"prénom: {prenom}")
    if ville:
        details.append(f"ville: {ville}")
    if signe:
        details.append(f"signe: {signe}")
    if interets:
        details.append(f"intérêts: {interets}")

    return f"Profil mis à jour avec succès ({', '.join(details)})."


def lire_profil() -> Dict[str, Any]:
    """Lit les données du profil utilisateur depuis la base SQLite."""
    t0 = time.time()
    profil = db.get_profil()
    duree_ms = int((time.time() - t0) * 1000)

    # Journalisation technique sans contenu personnel
    consigner_activite(
        etape="outil:lire_profil",
        detail="Lecture du profil utilisateur",
        duree_ms=duree_ms,
    )

    if not profil:
        return {"statut": "aucun profil enregistré"}

    # On ne renvoie que les champs utiles au modèle
    return {
        "prenom": profil.get("prenom"),
        "ville": profil.get("ville"),
        "signe": profil.get("signe"),
        "interets": profil.get("interets"),
    }


def ecrire_note(texte: str) -> str:
    """Enregistre une nouvelle note personnelle pour l'utilisateur."""
    t0 = time.time()
    db.ajouter_note(texte)
    duree_ms = int((time.time() - t0) * 1000)

    # Journalisation technique sans le texte de la note
    consigner_activite(
        etape="outil:ecrire_note",
        detail="Enregistrement d'une note",
        duree_ms=duree_ms,
    )
    return "Note enregistrée avec succès."


def lire_notes() -> List[Dict[str, Any]]:
    """Lit toutes les notes personnelles de l'utilisateur avec leur identifiant."""
    t0 = time.time()
    notes = db.get_notes(limite=None)
    duree_ms = int((time.time() - t0) * 1000)

    consigner_activite(
        etape="outil:lire_notes",
        detail="Lecture des notes",
        duree_ms=duree_ms,
    )
    return notes


def supprimer_note(id_note: Any) -> str:
    """Supprime une note personnelle par son identifiant numérique unique."""
    t0 = time.time()
    try:
        id_int = int(id_note)
        succes = db.supprimer_note(id_int)
    except (ValueError, TypeError):
        succes = False
        id_int = id_note
    duree_ms = int((time.time() - t0) * 1000)

    consigner_activite(
        etape="outil:supprimer_note",
        detail="Suppression d'une note",
        duree_ms=duree_ms,
    )
    if succes:
        return f"Note {id_int} supprimée avec succès."
    return f"Aucune note trouvée avec l'identifiant {id_int}."


def lire_pense_betes() -> List[Dict[str, Any]]:
    """Lit tous les pense-bêtes reçus par webhook avec leur identifiant et statut."""
    t0 = time.time()
    pense_betes = db.get_pense_betes(non_integres_seulement=False)
    duree_ms = int((time.time() - t0) * 1000)

    consigner_activite(
        etape="outil:lire_pense_betes",
        detail="Lecture des pense-bêtes",
        duree_ms=duree_ms,
    )
    return pense_betes


def supprimer_pense_bete(id_pense_bete: Any) -> str:
    """Supprime un pense-bête reçu par webhook par son identifiant numérique unique."""
    t0 = time.time()
    try:
        id_int = int(id_pense_bete)
        succes = db.supprimer_pense_bete(id_int)
    except (ValueError, TypeError):
        succes = False
        id_int = id_pense_bete
    duree_ms = int((time.time() - t0) * 1000)

    consigner_activite(
        etape="outil:supprimer_pense_bete",
        detail="Suppression d'un pense-bête",
        duree_ms=duree_ms,
    )
    if succes:
        return f"Pense-bête {id_int} supprimé avec succès."
    return f"Aucun pense-bête trouvé avec l'identifiant {id_int}."



def oublier_utilisateur() -> str:
    """Efface définitivement toutes les données personnelles de l'utilisateur."""
    t0 = time.time()
    db.effacer_donnees_utilisateur()
    # L'effacement a lieu au milieu d'un échange du chat : cet échange, qui contient
    # la demande d'oubli, ne doit pas être enregistré juste après.
    db.marquer_oubli_actif(True)
    duree_ms = int((time.time() - t0) * 1000)

    # Journalisation technique : "profil effacé" sans aucun contenu personnel
    consigner_activite(
        etape="outil:oublier_utilisateur",
        detail="profil effacé",
        duree_ms=duree_ms,
    )
    return "Toutes vos données (profil, notes, conversations et pense-bêtes) ont été définitivement effacées."


def lire_journal(execution: Optional[str] = None) -> Dict[str, Any]:
    """Lit les enregistrements du journal technique pour l'exécution spécifiée ou la dernière."""
    t0 = time.time()
    lignes = lire_journal_execution(execution_id=execution)
    duree_ms = int((time.time() - t0) * 1000)

    consigner_activite(
        etape="outil:lire_journal",
        detail="Lecture du journal d'activité",
        duree_ms=duree_ms,
    )

    if not lignes:
        return {"statut": "aucun enregistrement trouvé dans le journal"}

    resume_etapes = []
    total_entree = 0
    total_sortie = 0
    total_reflexion = 0

    for ligne in lignes:
        entree = ligne.get("tokens_entree") or 0
        sortie = ligne.get("tokens_sortie") or 0
        refl = ligne.get("tokens_reflexion") or 0
        total_entree += entree
        total_sortie += sortie
        total_reflexion += refl

        resume_etapes.append({
            "etape": ligne.get("etape"),
            "latence_ms": ligne.get("latence_ms"),
            "duree_ms": ligne.get("duree_ms"),
            "tokens_entree": entree if entree else None,
            "tokens_sortie": sortie if sortie else None,
            "tokens_reflexion": refl if refl else None,
        })

    cout_estime = formater_cout_usd(calculer_cout_usd(total_entree, total_sortie, total_reflexion))

    return {
        "execution_id": lignes[0].get("execution_id"),
        "nombre_etapes": len(lignes),
        "etapes": resume_etapes,
        "total_tokens_entree": total_entree,
        "total_tokens_sortie": total_sortie,
        "total_tokens_reflexion": total_reflexion,
        "cout_estime_usd": cout_estime,
    }


# Spécifications des outils pour l'API Google GenAI (Interactions)
OUTILS_SPEC: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "enregistrer_profil",
        "description": (
            "Enregistre ou met à jour les informations de profil de l'utilisateur "
            "(prénom, ville de résidence, centres d'intérêt, jour et mois de naissance). "
            "Le signe astrologique est calculé automatiquement sans stocker la date complète."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prenom": {
                    "type": "string",
                    "description": "Le prénom de l'utilisateur.",
                },
                "ville": {
                    "type": "string",
                    "description": "La ville de résidence de l'utilisateur.",
                },
                "interets": {
                    "type": "string",
                    "description": "Les centres d'intérêt, loisirs ou passions de l'utilisateur.",
                },
                "jour_naissance": {
                    "type": "integer",
                    "description": "Le jour de naissance (numéro de 1 à 31) si mentionné.",
                },
                "mois_naissance": {
                    "type": "integer",
                    "description": "Le mois de naissance (numéro de 1 à 12) si mentionné.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "lire_profil",
        "description": (
            "Consulte le profil mémorisé de l'utilisateur pour savoir ce que GoodVibe sait de lui "
            "(prénom, ville, signe astrologique, centres d'intérêt)."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "type": "function",
        "name": "ecrire_note",
        "description": (
            "Enregistre une note personnelle confiée par l'utilisateur."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "texte": {
                    "type": "string",
                    "description": "Le contenu textuel de la note à mémoriser.",
                },
            },
            "required": ["texte"],
        },
    },
    {
        "type": "function",
        "name": "lire_notes",
        "description": (
            "Consulte la liste complète de toutes les notes personnelles enregistrées de l'utilisateur, avec leur identifiant (id)."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "type": "function",
        "name": "supprimer_note",
        "description": (
            "Supprime définitivement une note personnelle par son identifiant numérique unique (id_note). "
            "RÈGLE STRICTE : Ne jamais appeler cet outil sans avoir d'abord cité à l'utilisateur le numéro "
            "et le texte exact de la note, et avoir obtenu sa confirmation explicite (un 'oui'). "
            "Si plusieurs notes correspondent ou aucune, poser la question au lieu d'appeler cet outil."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id_note": {
                    "type": "integer",
                    "description": "L'identifiant numérique unique de la note à supprimer.",
                },
            },
            "required": ["id_note"],
        },
    },
    {
        "type": "function",
        "name": "lire_pense_betes",
        "description": (
            "Consulte la liste complète de tous les pense-bêtes reçus par webhook, avec leur identifiant (id), leur texte et leur statut d'intégration."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "type": "function",
        "name": "supprimer_pense_bete",
        "description": (
            "Supprime définitivement un pense-bête reçu par webhook par son identifiant numérique unique (id_pense_bete). "
            "RÈGLE STRICTE : Ne jamais appeler cet outil sans avoir d'abord cité à l'utilisateur le numéro "
            "et le texte exact du pense-bête, et avoir obtenu sa confirmation explicite (un 'oui'). "
            "Si plusieurs pense-bêtes correspondent ou aucun, poser la question au lieu d'appeler cet outil."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "id_pense_bete": {
                    "type": "integer",
                    "description": "L'identifiant numérique unique du pense-bête à supprimer.",
                },
            },
            "required": ["id_pense_bete"],
        },
    },
    {
        "type": "function",
        "name": "oublier_utilisateur",
        "description": (
            "Efface définitivement toutes les données personnelles de l'utilisateur "
            "(profil, notes, conversations enregistrées). "
            "RÈGLE STRICTE : Cet outil ne doit JAMAIS être appelé sans confirmation "
            "explicite préalable de l'utilisateur."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "type": "function",
        "name": "meteo",
        "description": (
            "Obtient les prévisions météo réelles du jour pour une ville donnée "
            "(températures minimale et maximale, et état du ciel)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ville": {
                    "type": "string",
                    "description": "Le nom de la commune ou ville (ex: Paris, Lyon, Marseille).",
                },
            },
            "required": ["ville"],
        },
    },
    {
        "type": "function",
        "name": "lire_journal",
        "description": (
            "Consulte les enregistrements du journal d'activité technique pour "
            "expliquer à l'utilisateur ce que l'agent vient d'effectuer "
            "(étapes, outils appelés, tokens consommés, latence, durée et coût estimé)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "execution": {
                    "type": "string",
                    "description": (
                        "L'identifiant d'exécution facultatif. Si non spécifié, "
                        "consulte les détails de la dernière exécution enregistrée."
                    ),
                },
            },
        },
    },
    {
        "type": "function",
        "name": "obtenir_image_du_jour",
        "description": (
            "Permet de récupérer l'illustration générée pour le brief du jour. "
            "À appeler lorsque l'utilisateur demande à voir ou afficher l'image du jour dans la conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]


def obtenir_image_du_jour() -> Dict[str, Any]:
    """Récupère le chemin et l'état de l'illustration du jour pour affichage dans le chat."""
    from pathlib import Path

    from image import get_image_du_jour

    chemin = get_image_du_jour()
    if chemin:
        chemin_posix = Path(chemin).resolve().as_posix()
        url_file = f"/gradio_api/file={chemin_posix}"
        return {
            "statut": "disponible",
            "chemin": chemin,
            "url": url_file,
            "markdown": f"![Illustration du jour]({url_file})",
            "message": "L'illustration du jour est disponible.",
        }
    return {
        "statut": "non_generee",
        "message": "Aucune illustration n'a encore été produite pour aujourd'hui. Vous pouvez la générer depuis l'onglet 'Brief du jour'.",
    }


def obtenir_specifications_outils() -> Tuple[List[Dict[str, Any]], List[str]]:
    """Retourne l'ensemble des outils déclarés pour Gemini :
    les fonctions Python locales + les outils annoncés dynamiquement par le serveur MCP via list_tools.

    Returns:
        Un couple (outils, erreurs). Si le serveur MCP n'a pas démarré, son outil manque
        au catalogue et `erreurs` porte le message à donner au modèle : sans lui, l'outil
        disparaîtrait sans que le modèle ni l'utilisateur ne le sachent.
    """
    outils = list(OUTILS_SPEC)
    erreurs: List[str] = []
    try:
        outils.extend(lister_outils_mcp())
    except ServeurMCPNonDemarre:
        erreurs.append(ERREUR_SERVEUR_FETCH)
    return outils, erreurs


def executer_outil(nom: str, arguments: Dict[str, Any]) -> Any:
    """Exécute la fonction Python locale correspondant au nom de l'outil demandé."""
    args = arguments or {}
    if nom == "enregistrer_profil":
        return enregistrer_profil(
            prenom=args.get("prenom"),
            ville=args.get("ville"),
            interets=args.get("interets"),
            jour_naissance=args.get("jour_naissance"),
            mois_naissance=args.get("mois_naissance"),
        )
    elif nom == "lire_profil":
        return lire_profil()
    elif nom == "ecrire_note":
        return ecrire_note(texte=args.get("texte", ""))
    elif nom == "lire_notes":
        return lire_notes()
    elif nom == "supprimer_note":
        return supprimer_note(id_note=args.get("id_note"))
    elif nom == "lire_pense_betes":
        return lire_pense_betes()
    elif nom == "supprimer_pense_bete":
        return supprimer_pense_bete(id_pense_bete=args.get("id_pense_bete"))
    elif nom == "oublier_utilisateur":
        return oublier_utilisateur()
    elif nom == "meteo":
        return {"prevision": obtenir_meteo(ville=args.get("ville", ""))}
    elif nom == "fetch":
        # L'adresse lue est celle que horoscope.py construit à partir du signe du profil :
        # le modèle demande l'outil, il ne choisit pas ce que fetch va lire.
        return lire_horoscope_du_profil()
    elif nom == "lire_journal":
        return lire_journal(execution=args.get("execution"))
    elif nom == "obtenir_image_du_jour":
        return obtenir_image_du_jour()
    else:
        return f"Erreur : outil inconnu '{nom}'"

