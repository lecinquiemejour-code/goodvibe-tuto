# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Boucle d'agent autonome GoodVibe (Feature 1).

Gère l'orchestration du dialogue avec le modèle Gemini via l'API Interactions,
l'injection de la mémoire locale (profil et notes), l'exécution autonome des outils,
le streaming des réponses, la mesure des tokens/latence et le journal d'activité.
"""

import json
import logging
import time
from typing import Any, Dict, Generator, List, Optional

from google import genai

from config import (
    GEMINI_API_KEY,
    MAX_OUTPUT_TOKENS,
    MAX_TOURS,
    MODELE_TEXTE,
    THINKING_LEVEL,
    lire_prompt_systeme,
    verifier_config,
)
from db import get_notes, get_profil
from fragments import COULISSES, FLUX, RELEVE, REPONSE, Fragment
from horoscope import construire_url_horoscope
from journal import consigner_activite
from outils import executer_outil, obtenir_specifications_outils

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("goodvibe.agent")


def get_client() -> genai.Client:
    """Instancie le client officiel Google GenAI."""
    verifier_config()
    return genai.Client(api_key=GEMINI_API_KEY)


def repondre(
    message: str,
    historique: Optional[List[Dict[str, Any]]] = None,
    system_instruction: Optional[str] = None,
    voir_reflexion: bool = False,
    etape: str = "chat",
    detail: str = "Échange conversationnel",
    voir_flux: bool = False,
) -> Generator[Fragment, None, None]:
    """Exécute la boucle d'agent avec gestion autonome des outils et streaming.

    Args:
        message: Le message envoyé par l'utilisateur.
        historique: Le dialogue précédent, en texte simple : uniquement les messages
            de l'utilisateur et le texte des réponses (optionnel).
        system_instruction: Les instructions système personnalisées (optionnel).
        voir_reflexion: Si True, émet aussi les fragments de coulisses.
        voir_flux: Si True, émet aussi un fragment par événement brut reçu de Gemini.
            Seul un appelant qui a un panneau pour l'afficher le demande.

    Yields:
        Des fragments étiquetés (coulisses, réponse, relevé, flux), au fil de l'eau.
        L'appelant affiche tout, et ne retient que le texte des fragments de réponse.
    """
    logger.info("Début du tour d'inférence (modèle: %s)", MODELE_TEXTE)
    client = get_client()

    # Détection automatique si l'appel concerne le brief matinal
    if etape == "chat" and "brief matinal" in message.lower():
        etape = "brief"
        detail = "Génération du brief matinal"

    # Préparation du contexte d'entrée
    contexte_input = message
    if historique:
        lignes = []
        # L'historique reçu ne contient que le dialogue : les appelants n'y rangent
        # que le texte des fragments de réponse, jamais les coulisses ni le relevé.
        logger.info("Historique reçu : %d message(s)", len(historique))
        for h in historique:
            role = h.get("role", "user")
            texte = h.get("content", "")
            lignes.append(f"{role.capitalize()}: {texte}")
        lignes.append(f"User: {message}")
        contexte_input = "\n".join(lignes)

    if system_instruction is not None:
        prompt_actif = system_instruction
    else:
        try:
            prompt_actif = lire_prompt_systeme()
        except FileNotFoundError as e:
            # Sans sa fiche de poste, GoodVibe n'a plus ses règles (confirmation avant un
            # effacement, erreurs d'outils écrites telles quelles) : il le dit et ne répond pas.
            logger.error("Prompt système introuvable : %s", e)
            consigner_activite(etape=etape, detail=f"Échec : {e}")
            yield Fragment(
                nature=REPONSE,
                texte=f"[Erreur : {e}. GoodVibe ne peut pas répondre sans sa fiche de poste.]",
            )
            return

    # Les outils sont demandés une fois par réponse : les fonctions locales, puis ceux que
    # le serveur MCP annonce. La même liste repart ensuite à chaque tour de la boucle.
    outils_disponibles, erreurs_outils = obtenir_specifications_outils()
    if erreurs_outils:
        # Le serveur MCP n'a pas démarré : son outil manque au catalogue. Le modèle reçoit
        # l'erreur, pour l'écrire telle quelle au lieu d'inventer le contenu attendu.
        logger.warning("Outils indisponibles pour cette réponse : %s", erreurs_outils)
        prompt_actif += (
            "\n\n### Outils indisponibles pour cette réponse :\n"
            + "\n".join(f"- {erreur}" for erreur in erreurs_outils)
            + "\nSi la demande a besoin de l'un de ces contenus, écris ce message d'erreur tel quel "
            "à sa place, sans rien inventer."
        )
        if voir_reflexion:
            yield Fragment(
                nature=COULISSES,
                titre="🛠️ Outil indisponible",
                texte="```text\n" + "\n".join(erreurs_outils) + "\n```",
            )

    # Règle Fiche 4 : injection du profil et des notes UNE FOIS au démarrage dans le prompt système
    contexte_memoire = []
    profil = get_profil()
    if profil:
        details = []
        if profil.get("prenom"):
            details.append(f"Prénom: {profil['prenom']}")
        if profil.get("signe"):
            details.append(f"Signe astrologique: {profil['signe']}")
            # Fiche 8 : l'adresse de l'horoscope est construite par notre code, à partir du
            # signe du profil. Le modèle la passe à fetch, il ne la compose pas.
            url_horoscope = construire_url_horoscope(profil["signe"])
            if url_horoscope:
                details.append(f"Adresse de l'horoscope du jour (pour l'outil fetch): {url_horoscope}")
        if profil.get("ville"):
            details.append(f"Ville: {profil['ville']}")
        if profil.get("interets"):
            details.append(f"Centres d'intérêt: {profil['interets']}")
        if details:
            contexte_memoire.append("Profil utilisateur actuel :\n- " + "\n- ".join(details))

    notes = get_notes(limite=5)
    if notes:
        lignes_notes = [f"- {n['texte']}" for n in notes]
        contexte_memoire.append("Notes récentes mémorisées :\n" + "\n".join(lignes_notes))

    if contexte_memoire:
        prompt_actif += "\n\n### Mémoire actuelle de GoodVibe :\n" + "\n\n".join(contexte_memoire)

    tour_actuel = 1
    interaction_id = None
    input_actif: Any = contexte_input

    t_debut = time.time()
    t_premier_fragment = None
    total_tokens_entree = 0
    total_tokens_sortie = 0
    total_tokens_reflexion = 0

    thought_chunks = []
    thought_emitted = False
    a_reflechi = False

    try:
        while tour_actuel <= MAX_TOURS:
            # Construction des paramètres de l'interaction
            if interaction_id is None:
                params: Dict[str, Any] = {
                    "model": MODELE_TEXTE,
                    "input": input_actif,
                    "system_instruction": prompt_actif,
                    "tools": outils_disponibles,
                    "stream": True,
                    "generation_config": {
                        "max_output_tokens": MAX_OUTPUT_TOKENS,
                        "thinking_level": THINKING_LEVEL,
                        "thinking_summaries": "auto",
                    },
                }
            else:
                # L'API Interactions ne conserve d'un appel à l'autre que la conversation.
                # Le prompt système (avec le profil) et les outils doivent donc être renvoyés
                # à chaque tour, y compris quand on rend au modèle le résultat d'un outil.
                # Sans eux, il rédige sa réponse sans savoir qui il est ni à qui il parle.
                logger.info("Tour %d : renvoi du prompt système et des outils", tour_actuel)
                params = {
                    "model": MODELE_TEXTE,
                    "previous_interaction_id": interaction_id,
                    "input": input_actif,
                    "system_instruction": prompt_actif,
                    "tools": outils_disponibles,
                    "stream": True,
                    "generation_config": {
                        "max_output_tokens": MAX_OUTPUT_TOKENS,
                        "thinking_level": THINKING_LEVEL,
                        "thinking_summaries": "auto",
                    },
                }

            # Si l'utilisateur a activé la visualisation des coulisses, on affiche la requête repliée par défaut
            if voir_reflexion:
                payload_json = json.dumps(params, ensure_ascii=False, indent=2)
                yield Fragment(
                    nature=COULISSES,
                    titre=f"📤 Requête envoyée à Google Gemini (Tour {tour_actuel})",
                    texte=f"```json\n{payload_json}\n```",
                    replie=True,
                )

            stream = client.interactions.create(**params)
            appels_outils = []
            call_en_cours = None
            arg_chunks = []
            nb_evenements = 0

            for event in stream:
                nb_evenements += 1
                # Le flux brut : l'événement part tel quel vers son panneau, avant tout
                # traitement. En streaming, Gemini n'envoie jamais la réponse en un seul
                # JSON : c'est cette suite d'événements qu'on montre.
                if voir_flux:
                    yield Fragment(
                        nature=FLUX,
                        evenement=event.model_dump(mode="json", exclude_none=True),
                        tour=tour_actuel,
                    )

                # Capture de l'identifiant d'interaction pour le chaînage
                interaction = getattr(event, "interaction", None)
                if interaction and hasattr(interaction, "id") and interaction.id:
                    interaction_id = interaction.id

                event_type = getattr(event, "event_type", None)
                step = getattr(event, "step", None)
                delta = getattr(event, "delta", None)
                stype = getattr(step, "type", None) if step else None
                dtype = getattr(delta, "type", None) if delta else None

                # Détection d'un appel d'outil
                if stype == "function_call":
                    call_en_cours = step
                    arg_chunks = []

                elif dtype == "arguments_delta":
                    arg_chunks.append(getattr(delta, "arguments", ""))

                elif event_type == "step.stop" and call_en_cours:
                    arguments_complets = {}
                    if arg_chunks:
                        try:
                            arguments_complets = json.loads("".join(arg_chunks))
                        except Exception:
                            arguments_complets = {}
                    appels_outils.append({
                        "id": call_en_cours.id,
                        "name": call_en_cours.name,
                        "arguments": arguments_complets,
                    })
                    call_en_cours = None
                    arg_chunks = []

                # Capture de la réflexion interne
                elif stype == "thought" or dtype in ("thought_summary", "thought_signature"):
                    a_reflechi = True
                    if dtype == "thought_summary":
                        content = getattr(delta, "content", None)
                        txt = getattr(content, "text", "")
                        if txt:
                            thought_chunks.append(txt)

                # Capture et streaming du texte final de réponse
                elif dtype == "text" or (delta and hasattr(delta, "text")):
                    if t_premier_fragment is None:
                        t_premier_fragment = time.time()

                    if voir_reflexion and not thought_emitted and (thought_chunks or a_reflechi):
                        pensee = "".join(thought_chunks).strip()
                        texte_affiche = (
                            pensee
                            if pensee
                            else "Le modèle n'a pas rédigé de résumé de réflexion pour cette étape."
                        )
                        yield Fragment(
                            nature=COULISSES,
                            titre="💭 Résumé de réflexion :",
                            texte=f"```text\n{texte_affiche}\n```",
                        )
                        thought_emitted = True

                    texte_recu = getattr(delta, "text", "")
                    if texte_recu:
                        yield Fragment(nature=REPONSE, texte=texte_recu)

                elif event_type == "interaction.completed":
                    # Cumul des tokens officiels
                    if interaction and hasattr(interaction, "usage") and interaction.usage:
                        u = interaction.usage
                        if hasattr(u, "total_input_tokens") and u.total_input_tokens:
                            total_tokens_entree += u.total_input_tokens
                        if hasattr(u, "total_output_tokens") and u.total_output_tokens:
                            total_tokens_sortie += u.total_output_tokens
                        if hasattr(u, "total_thought_tokens") and u.total_thought_tokens:
                            total_tokens_reflexion += u.total_thought_tokens

                elif event_type == "error":
                    logger.error("Événement d'erreur reçu : %s", event)
                    yield Fragment(
                        nature=REPONSE,
                        texte=f"\n[Erreur : {getattr(event, 'error', 'Erreur de streaming')}]",
                    )

            # Journalisation de la quantité uniquement : les événements contiennent le texte
            # de la réponse et les arguments des outils, qui ne s'écrivent dans aucun log.
            logger.info("Tour %d : %d événement(s) reçu(s) de Gemini", tour_actuel, nb_evenements)

            # Si des outils ont été appelés par le modèle, on les exécute et on enchaîne le tour suivant
            if appels_outils:
                # Si le modèle a produit une réflexion avant d'appeler un outil, on l'affiche en premier dans les coulisses
                if voir_reflexion and not thought_emitted and (thought_chunks or a_reflechi):
                    pensee = "".join(thought_chunks).strip()
                    texte_affiche = (
                        pensee
                        if pensee
                        else "Le modèle n'a pas rédigé de résumé de réflexion pour cette étape."
                    )
                    yield Fragment(
                        nature=COULISSES,
                        titre="💭 Résumé de réflexion :",
                        texte=f"```text\n{texte_affiche}\n```",
                    )
                    thought_emitted = True

                resultats = []
                for call in appels_outils:
                    nom = call["name"]
                    args = call["arguments"]
                    logger.info("Exécution de l'outil autonome: %s (args: %s)", nom, list(args.keys()))
                    res = executer_outil(nom, args)

                    # Si l'utilisateur a activé la visualisation des coulisses, on affiche le JSON
                    if voir_reflexion:
                        args_json = json.dumps(args, ensure_ascii=False, indent=2)
                        res_dict = res if isinstance(res, dict) else {"message": str(res)}
                        res_json = json.dumps(res_dict, ensure_ascii=False, indent=2)
                        yield Fragment(
                            nature=COULISSES,
                            titre=f"🛠️ Appel d'outil : {nom}",
                            texte=(
                                f"```json\n{args_json}\n```\n"
                                f"> 📋 **Résultat renvoyé à l'IA :**\n"
                                f"```json\n{res_json}\n```"
                            ),
                            # Le nom et le résultat voyagent à part du texte affiché :
                            # le brief y lit la météo et l'horoscope pour l'image.
                            outil=nom,
                            resultat=res_dict,
                        )

                    resultats.append({
                        "type": "function_result",
                        "call_id": call["id"],
                        "name": nom,
                        "result": res if isinstance(res, dict) else {"message": str(res)},
                    })
                input_actif = resultats
                tour_actuel += 1
            else:
                # Aucun outil appelé, la réponse textuelle a été délivrée
                break

        if tour_actuel > MAX_TOURS:
            logger.warning("Limite maximale de tours (%d) atteinte.", MAX_TOURS)
            yield Fragment(
                nature=REPONSE,
                texte="\n[Arrêt de sécurité : nombre maximal de tours atteint]",
            )

        t_fin = time.time()
        latence_ms = int((t_premier_fragment - t_debut) * 1000) if t_premier_fragment else int((t_fin - t_debut) * 1000)
        duree_ms = int((t_fin - t_debut) * 1000)

        # Consignation au journal sans donnée personnelle
        consigner_activite(
            etape=etape,
            detail=detail,
            tokens_entree=total_tokens_entree or None,
            tokens_sortie=total_tokens_sortie or None,
            tokens_reflexion=total_tokens_reflexion or None,
            latence_ms=latence_ms,
            duree_ms=duree_ms,
        )

        # Relevé officiel sous chaque réponse (chat comme brief)
        # Les chiffres voyagent à part du texte : qui en a besoin (le bilan du brief)
        # les lit dans le fragment, jamais dans la phrase affichée.
        yield Fragment(
            nature=RELEVE,
            texte=(
                f"Tokens : {total_tokens_entree or 0} entrée, {total_tokens_reflexion or 0} réflexion, "
                f"{total_tokens_sortie or 0} sortie — "
                f"Tours : {tour_actuel} — "
                f"Premier mot : {latence_ms} ms — "
                f"Durée totale : {duree_ms} ms"
            ),
            chiffres={
                "tokens_entree": total_tokens_entree or 0,
                "tokens_reflexion": total_tokens_reflexion or 0,
                "tokens_sortie": total_tokens_sortie or 0,
                "tours": tour_actuel,
                "latence_ms": latence_ms,
                "duree_ms": duree_ms,
            },
        )

        logger.info(
            "Fin du tour (latence: %d ms, durée: %d ms, tokens E/S/R: %s/%s/%s, tours: %d)",
            latence_ms,
            duree_ms,
            total_tokens_entree,
            total_tokens_sortie,
            total_tokens_reflexion,
            tour_actuel,
        )

    except Exception as e:
        logger.exception("Erreur lors de la boucle d'agent : %s", e)
        yield Fragment(
            nature=REPONSE,
            texte=f"\n[Erreur de communication avec GoodVibe : {e}]",
        )
