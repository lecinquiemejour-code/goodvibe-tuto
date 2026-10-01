# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Module de génération de l'illustration du jour de GoodVibe (Feature 10).

Responsabilité unique :
- Composer un prompt visuel court et artistique via le modèle texte Gemini, à partir
  de quatre éléments : la météo, la ville, l'horoscope et les centres d'intérêt.
  La consigne envoyée au modèle texte vit dans prompt_image.md, pas dans ce fichier :
  le code n'y insère que la liste des éléments disponibles.
- Générer l'illustration via le modèle image Gemini (MODELE_IMAGE) avec l'API Interactions.
- Sauvegarder l'image sur disque dans data/images/AAAA-MM-JJ.png.
- Appliquer le verrou anti-doublon SQLite (clé 'image-AAAA-MM-JJ' dans la table traites).
- Fournir les blocs repliables des requêtes brutes envoyées à Gemini (transparence totale des coulisses).
- Rendre un message d'erreur qui dit ce qui a échoué si le prompt visuel ou l'image ne sort pas :
  ni image de remplacement, ni prompt écrit d'avance, ni élément inventé.
"""

import base64
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from google import genai

from config import (
    DOSSIER_IMAGES,
    GEMINI_API_KEY,
    MODELE_IMAGE,
    MODELE_TEXTE,
    PROMPT_IMAGE_PATH,
    verifier_config,
)
from db import est_deja_traite, marquer_traite
from journal import consigner_activite

logger = logging.getLogger("goodvibe.image")

# L'endroit de prompt_image.md où le code insère la liste des éléments disponibles
MARQUEUR_ELEMENTS = "{elements}"


def get_client() -> genai.Client:
    """Instancie le client officiel Google GenAI."""
    verifier_config()
    return genai.Client(api_key=GEMINI_API_KEY)


def get_image_du_jour(date_jour: Optional[str] = None) -> Optional[str]:
    """Renvoie le chemin de l'illustration du jour si elle existe déjà sur disque."""
    date_str = date_jour or datetime.now().strftime("%Y-%m-%d")
    chemin_image = DOSSIER_IMAGES / f"{date_str}.png"
    if chemin_image.exists():
        return str(chemin_image)
    return None


def _retirer_image_perimee(chemin_fichier: Path) -> None:
    """Supprime l'image du jour restée sur le disque quand une nouvelle génération échoue.

    L'image du jour est celle du dernier brief, ou il n'y en a pas : sans ce retrait,
    l'image d'un brief précédent reviendrait au rechargement de la page et dans le chat,
    à côté d'un brief qui annonce une erreur.

    Args:
        chemin_fichier: Le chemin de l'image du jour (data/images/AAAA-MM-JJ.png).
    """
    if chemin_fichier.exists():
        chemin_fichier.unlink()
        logger.info("Image du jour retirée après l'échec de sa régénération : %s", chemin_fichier.name)


def supprimer_toutes_les_images() -> int:
    """Retire du disque toutes les illustrations produites, lors d'un « Oublie-moi ».

    Une image du jour est tirée du profil (la ville, les centres d'intérêt) et de
    l'horoscope : c'est une donnée dérivée, qui part avec le reste.

    Returns:
        Le nombre de fichiers retirés.
    """
    if not DOSSIER_IMAGES.exists():
        return 0
    fichiers = [f for f in DOSSIER_IMAGES.iterdir() if f.is_file()]
    for fichier in fichiers:
        fichier.unlink()
    logger.info("[IMAGE] %d illustration(s) retirée(s) du disque", len(fichiers))
    return len(fichiers)


def _element_disponible(valeur: Optional[str]) -> str:
    """Rend la valeur nettoyée d'un élément, ou "" s'il est absent ou en erreur.

    Un élément absent reste absent : aucune valeur par défaut ne le remplace.
    """
    texte = (valeur or "").strip()
    if texte.startswith("Erreur :"):
        return ""
    return texte


def lire_consigne_image() -> str:
    """Lit la consigne du directeur artistique dans prompt_image.md.

    Returns:
        Le texte de la consigne, avec son marqueur {elements}.

    Raises:
        FileNotFoundError: si le fichier est absent. Aucune consigne de secours n'existe
            dans le code : l'appelant en fait un message d'erreur.
        ValueError: si le marqueur {elements} manque dans le fichier.
    """
    if not PROMPT_IMAGE_PATH.exists():
        raise FileNotFoundError(f"le fichier {PROMPT_IMAGE_PATH.name} est introuvable")
    consigne = PROMPT_IMAGE_PATH.read_text(encoding="utf-8").strip()
    if MARQUEUR_ELEMENTS not in consigne:
        raise ValueError(f"le marqueur {MARQUEUR_ELEMENTS} manque dans {PROMPT_IMAGE_PATH.name}")
    return consigne


def rediger_consigne_prompt_visuel(
    meteo: Optional[str] = None,
    ville: Optional[str] = None,
    horoscope: Optional[str] = None,
    interets: Optional[str] = None,
) -> str:
    """Rédige la consigne envoyée au modèle texte pour qu'il compose le prompt visuel.

    Le texte vient de prompt_image.md ; le code n'y insère que la liste des éléments
    disponibles. Fonction sans appel au modèle : elle se teste seule.

    Args:
        meteo: La météo du jour (absente ou en erreur : elle n'entre pas dans la consigne).
        ville: La ville du profil (si renseignée).
        horoscope: L'horoscope du jour (absent ou en erreur : il n'entre pas dans la consigne).
        interets: Les centres d'intérêt du profil (si renseignés).

    Returns:
        La consigne complète. Elle ne cite que les éléments disponibles.

    Raises:
        FileNotFoundError, ValueError: si prompt_image.md est absent ou sans marqueur.
    """
    # Un élément absent ou en erreur n'a pas de ligne : rien n'est inventé pour le remplacer
    candidats = [
        ("City", _element_disponible(ville)),
        ("Weather", _element_disponible(meteo)),
        ("Horoscope", _element_disponible(horoscope)),
        ("Personal interests", _element_disponible(interets)),
    ]
    lignes = [f"- {nom}: {valeur}" for nom, valeur in candidats if valeur]
    elements = "\n".join(lignes) if lignes else "None"
    logger.info("Consigne du prompt visuel : %d élément(s) disponible(s) sur 4", len(lignes))

    return lire_consigne_image().replace(MARQUEUR_ELEMENTS, elements)


def composer_prompt_visuel(
    meteo: Optional[str] = None,
    ville: Optional[str] = None,
    horoscope: Optional[str] = None,
    interets: Optional[str] = None,
) -> Tuple[str, str, int, int]:
    """Fait composer un prompt visuel artistique en anglais par le modèle texte Gemini,
    à partir des quatre éléments de la fiche 10.

    Args:
        meteo: Données météo réelles (si disponibles et hors erreur).
        ville: Ville de résidence de l'utilisateur (si renseignée).
        horoscope: Horoscope du jour (si disponible et hors erreur).
        interets: Centres d'intérêt de l'utilisateur (si renseignés).

    Returns:
        Un tuple (prompt_visuel, consigne_envoyee, tokens_entree, tokens_sortie).

    Raises:
        ValueError: si le modèle texte rend une réponse vide. Aucun prompt écrit
            d'avance ne prend sa place : l'appelant en fait un message d'erreur.
    """
    t0 = time.time()
    client = get_client()

    consigne = rediger_consigne_prompt_visuel(
        meteo=meteo, ville=ville, horoscope=horoscope, interets=interets
    )
    logger.info("Composition du prompt visuel demandée au modèle %s", MODELE_TEXTE)

    response = client.interactions.create(
        model=MODELE_TEXTE,
        input=consigne,
    )

    prompt_visuel = (response.output_text or "").strip()
    if not prompt_visuel:
        raise ValueError(f"le modèle texte {MODELE_TEXTE} a rendu un prompt visuel vide")

    duree_ms = int((time.time() - t0) * 1000)
    entree = getattr(response.usage, "input_tokens", 0) or 0
    sortie = getattr(response.usage, "output_tokens", 0) or 0

    # Le prompt visuel cite la ville et les centres d'intérêt : il se lit dans les coulisses,
    # jamais dans le journal ni dans les logs. On n'y note que le fait, sa durée et ses tokens.
    consigner_activite(
        etape="image_prompt",
        detail="Prompt visuel composé",
        tokens_entree=entree,
        tokens_sortie=sortie,
        duree_ms=duree_ms,
    )
    logger.info("Prompt visuel composé : %d caractères (en %d ms)", len(prompt_visuel), duree_ms)

    return prompt_visuel, consigne, entree, sortie


def generer_illustration(
    meteo: Optional[str] = None,
    ville: Optional[str] = None,
    horoscope: Optional[str] = None,
    interets: Optional[str] = None,
    date_jour: Optional[str] = None,
    forcer: bool = False,
) -> Tuple[Optional[str], str, str, dict]:
    """Génère l'illustration quotidienne ou recharge celle existante.

    Respecte les exigences strictes de la Fiche 10 :
    - Quatre éléments : la météo, la ville, l'horoscope et les centres d'intérêt.
    - Anti-doublon via la clé 'image-AAAA-MM-JJ' dans la table SQLite 'traites'.
    - Transparence : génère les volets repliables des requêtes brutes de création d'image.
    - Message d'erreur explicite sans image de remplacement si le prompt visuel ou l'image échoue.
      Une image produite plus tôt dans la journée est alors retirée du disque.

    Args:
        meteo: La météo du jour, telle que l'outil l'a rendue (ou vide).
        ville: La ville du profil (ou vide).
        horoscope: L'horoscope du jour, tel que l'outil l'a rendu (ou vide).
        interets: Les centres d'intérêt du profil (ou vide).
        date_jour: La date de l'image (AAAA-MM-JJ) ; aujourd'hui par défaut.
        forcer: Si True, régénère l'image même si elle existe déjà.

    Returns:
        Un tuple (chemin_image_ou_None, statut_ou_erreur, bloc_coulisses_markdown, stats_dict).
    """
    date_str = date_jour or datetime.now().strftime("%Y-%m-%d")
    cle_verrou = f"image-{date_str}"
    DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
    chemin_fichier = DOSSIER_IMAGES / f"{date_str}.png"

    # 1. Vérification du verrou anti-doublon SQLite
    if not forcer and est_deja_traite(cle_verrou):
        if chemin_fichier.exists():
            logger.info("Image du jour déjà produite pour le %s : %s", date_str, chemin_fichier)
            payload_recharge = {
                "model": MODELE_IMAGE,
                "input": f"Illustration existante rechargée depuis {chemin_fichier.name}",
                "statut": "deja_produite_aujourdhui",
            }
            bloc_coulisses = (
                f"<details style='margin-top: 8px; margin-bottom: 12px;'>\n"
                f"<summary style='cursor: pointer;'>🎨 📤 <b>Requête envoyée à Google Gemini (Création de l'image)</b> <i>(cliquer pour déplier le JSON)</i></summary>\n\n"
                f"```json\n{json.dumps(payload_recharge, ensure_ascii=False, indent=2)}\n```\n\n"
                f"</details>\n\n"
            )
            return str(chemin_fichier), "Illustration du jour déjà disponible", bloc_coulisses, {
                "tokens_entree": 0,
                "tokens_sortie": 0,
                "nb_images": 0,
                "deja_produite": True,
                "duree_ms": 0,
            }

    # 2. Composition du prompt par le modèle texte, à partir des quatre éléments
    tokens_in = 0
    tokens_out = 0
    t_debut = time.time()
    try:
        prompt_visuel, consigne_prompt, tokens_in, tokens_out = composer_prompt_visuel(
            meteo=meteo,
            ville=ville,
            horoscope=horoscope,
            interets=interets,
        )
    except Exception as e:
        logger.warning("Échec composition prompt visuel : %s", e)
        duree_err = int((time.time() - t_debut) * 1000)
        consigner_activite(
            etape="image_generation",
            detail=f"Échec composition prompt visuel : {e}",
            duree_ms=duree_err,
        )
        _retirer_image_perimee(chemin_fichier)
        msg_err = f"Erreur : illustration non générée, impossible de composer le prompt visuel ({e})"
        return None, msg_err, "", {
            "tokens_entree": 0,
            "tokens_sortie": 0,
            "nb_images": 0,
            "deja_produite": False,
            "duree_ms": duree_err,
        }

    payload_prompt = {
        "model": MODELE_TEXTE,
        "input": consigne_prompt,
        "reponse_prompt_visuel": prompt_visuel,
    }
    payload_image = {
        "model": MODELE_IMAGE,
        "input": prompt_visuel,
    }

    bloc_coulisses = (
        f"<details style='margin-top: 12px; margin-bottom: 6px;'>\n"
        f"<summary style='cursor: pointer;'>📝 📤 <b>Requête envoyée à Google Gemini (Composition du prompt visuel)</b> <i>(cliquer pour déplier le JSON)</i></summary>\n\n"
        f"```json\n{json.dumps(payload_prompt, ensure_ascii=False, indent=2)}\n```\n\n"
        f"</details>\n\n"
        f"> 💡 📥 **Prompt visuel composé par le Directeur Artistique :**\n"
        f"> *« {prompt_visuel} »*\n\n"
        f"<details style='margin-top: 8px; margin-bottom: 12px;'>\n"
        f"<summary style='cursor: pointer;'>🎨 📤 <b>Requête envoyée à Google Gemini (Création de l'image)</b> <i>(cliquer pour déplier le JSON)</i></summary>\n\n"
        f"```json\n{json.dumps(payload_image, ensure_ascii=False, indent=2)}\n```\n\n"
        f"</details>\n\n"
    )

    # 3. Appel du modèle image via l'API Interactions Google GenAI
    t0 = time.time()
    try:
        client = get_client()
        logger.info("Envoi de la requête de génération d'image au modèle %s...", MODELE_IMAGE)

        response = client.interactions.create(
            model=MODELE_IMAGE,
            input=prompt_visuel,
        )

        output_image = getattr(response, "output_image", None)
        image_b64 = getattr(output_image, "data", None) if output_image else None

        if not image_b64:
            raise ValueError(f"Réponse sans données d'image reçue du modèle {MODELE_IMAGE}")

        # Décodage de l'image en base64 et enregistrement sur le disque local
        image_bytes = base64.b64decode(image_b64)
        chemin_fichier.write_bytes(image_bytes)

        duree_ms = int((time.time() - t0) * 1000)

        # Enregistrement du verrou anti-doublon et consigne au journal
        marquer_traite(cle_verrou)
        consigner_activite(
            etape="image_generation",
            detail=f"Illustration générée ({len(image_bytes)} octets) avec {MODELE_IMAGE}",
            duree_ms=duree_ms,
        )
        logger.info("Illustration sauvegardée dans %s (%d ms)", chemin_fichier, duree_ms)

        stats = {
            "tokens_entree": tokens_in,
            "tokens_sortie": tokens_out,
            "nb_images": 1,
            "deja_produite": False,
            "duree_ms": duree_ms,
        }
        return str(chemin_fichier), prompt_visuel, bloc_coulisses, stats

    except Exception as e:
        # Message d'erreur factuel sans image de remplacement
        duree_ms = int((time.time() - t0) * 1000)
        logger.error("Échec de la génération de l'illustration (%s) : %s", MODELE_IMAGE, e)
        consigner_activite(
            etape="image_generation",
            detail=f"Échec génération image ({MODELE_IMAGE}) : {type(e).__name__} - {str(e)[:100]}",
            duree_ms=duree_ms,
        )
        payload_erreur = {
            "model": MODELE_IMAGE,
            "input": prompt_visuel,
            "erreur": str(e),
        }
        bloc_coulisses_erreur = (
            f"<details style='margin-top: 8px; margin-bottom: 12px;'>\n"
            f"<summary style='cursor: pointer;'>⚠️ 📤 <b>Requête envoyée à Google Gemini (Création de l'image — Échec)</b> <i>(cliquer pour déplier le JSON)</i></summary>\n\n"
            f"```json\n{json.dumps(payload_erreur, ensure_ascii=False, indent=2)}\n```\n\n"
            f"</details>\n\n"
        )
        stats_erreur = {
            "tokens_entree": tokens_in,
            "tokens_sortie": tokens_out,
            "nb_images": 0,
            "deja_produite": False,
            "duree_ms": duree_ms,
        }
        _retirer_image_perimee(chemin_fichier)
        message_erreur = f"Erreur : illustration non générée, le modèle image {MODELE_IMAGE} a échoué ({e})"
        return None, message_erreur, bloc_coulisses_erreur, stats_erreur
