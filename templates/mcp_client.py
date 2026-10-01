# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Client standard MCP (Model Context Protocol) pour GoodVibe (Feature 8).

Gère la communication inter-processus via stdio avec le serveur MCP officiel
(mcp-server-fetch), l'interrogation des outils disponibles, la conversion de
leurs schémas vers le format Gemini et l'exécution d'appels d'outils.

Ce client est générique : il ne sait pas à quoi sert l'outil appelé. Quand un appel
échoue, il lève une erreur qui dit où la chaîne a cassé (le serveur, ou l'outil) ;
c'est l'appelant qui en fait un message pour l'utilisateur.
"""

import asyncio
import concurrent.futures
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import MCP_FETCH_ARGS, MCP_FETCH_COMMAND
from journal import consigner_activite

logger = logging.getLogger("goodvibe.mcp")

# Les trois issues possibles d'un appel d'outil
ISSUE_OK = "ok"
ISSUE_SERVEUR = "serveur"  # le serveur MCP n'a pas démarré
ISSUE_OUTIL = "outil"  # le serveur a démarré, mais l'outil a rendu une erreur

# La liste des outils annoncée par le serveur, retenue tant que le programme tourne :
# elle ne change pas d'un message à l'autre, et la redemander coûte près d'une seconde.
# None : pas encore demandée, ou la dernière demande a échoué (on la reposera).
_outils_en_memoire: Optional[List[Dict[str, Any]]] = None


class ErreurMCP(Exception):
    """Erreur d'un appel MCP : la classe fille dit où la chaîne a cassé."""


class ServeurMCPNonDemarre(ErreurMCP):
    """Le serveur MCP n'a pas pu être lancé, ou n'a pas répondu à la poignée de main."""


class OutilMCPEnEchec(ErreurMCP):
    """Le serveur a démarré, mais l'outil a rendu une erreur (source muette, refus, délai)."""


def get_server_params() -> StdioServerParameters:
    """Retourne les paramètres de configuration du serveur MCP fetch."""
    return StdioServerParameters(
        command=MCP_FETCH_COMMAND,
        args=MCP_FETCH_ARGS,
        env=None,
    )


async def _async_lister_outils() -> List[Dict[str, Any]]:
    """Interroge le serveur MCP pour lister les outils et les convertir au format Gemini."""
    params = get_server_params()
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            resultat = await session.list_tools()
            outils_convertis = []
            for t in resultat.tools:
                schema = t.input_schema or {"type": "object", "properties": {}}
                outils_convertis.append({
                    "type": "function",
                    "name": t.name,
                    "description": t.description or f"Outil MCP {t.name}",
                    "parameters": schema,
                })
            return outils_convertis


async def _async_appeler_outil(nom: str, arguments: Dict[str, Any]) -> Tuple[str, str]:
    """Exécute un outil via le serveur MCP en transport stdio.

    L'issue est rendue, pas levée : une exception levée à l'intérieur de la connexion
    en ressortirait enveloppée dans un groupe d'exceptions, et perdrait sa nature.

    Returns:
        Un couple (issue, texte) : le texte lu si l'issue est ISSUE_OK, sinon la cause technique.
    """
    params = get_server_params()
    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                try:
                    await session.initialize()
                except Exception as e_init:
                    return ISSUE_SERVEUR, f"{type(e_init).__name__} : {e_init}"

                try:
                    res = await session.call_tool(nom, arguments=arguments or {})
                except Exception as e_call:
                    return ISSUE_OUTIL, f"{type(e_call).__name__} : {e_call}"

                morceaux = []
                for content in res.content:
                    if hasattr(content, "text"):
                        morceaux.append(content.text)
                    elif hasattr(content, "data"):
                        morceaux.append(str(content.data))
                    else:
                        morceaux.append(str(content))
                texte_brut = "\n".join(morceaux).strip()

                # Détection d'une erreur renvoyée par le serveur ou par la source lue
                est_erreur = getattr(res, "isError", False)
                if est_erreur or "Failed to fetch" in texte_brut or "status code" in texte_brut.lower():
                    return ISSUE_OUTIL, texte_brut

                return ISSUE_OK, texte_brut
    except Exception as e_start:
        return ISSUE_SERVEUR, f"{type(e_start).__name__} : {e_start}"


def lister_outils_mcp() -> List[Dict[str, Any]]:
    """Interface synchrone pour lister les outils MCP convertis pour Gemini.

    Interroge dynamiquement le serveur officiel via list_tools, une fois : la liste est
    ensuite retenue tant que le programme tourne. Un échec n'est pas retenu : la question
    est reposée à l'appel suivant.
    Ne contient AUCUNE définition de secours statique (Fiche 8).

    Returns:
        Les outils annoncés par le serveur, au format de Gemini.

    Raises:
        ServeurMCPNonDemarre: si le serveur n'a pas pu annoncer ses outils. Sans cette
            erreur, l'outil disparaîtrait du catalogue sans que personne ne le sache.
    """
    global _outils_en_memoire
    if _outils_en_memoire is not None:
        # Des copies : l'appelant ne peut pas modifier la liste retenue
        return [dict(outil) for outil in _outils_en_memoire]

    t0 = time.time()
    try:
        # Exécution dans un thread dédié pour éviter tout conflit avec les boucles d'événements existantes
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(_async_lister_outils()))
            outils = future.result(timeout=15.0)
    except Exception as e:
        logger.warning("Le serveur MCP n'a pas annoncé ses outils : %s", e)
        consigner_activite(
            etape="mcp:list_tools",
            detail=f"Échec : le serveur MCP n'a pas démarré ({type(e).__name__})",
            duree_ms=int((time.time() - t0) * 1000),
        )
        raise ServeurMCPNonDemarre(str(e)) from e

    logger.info(
        "Serveur MCP : %d outil(s) annoncé(s) en %d ms, liste retenue jusqu'à l'arrêt du programme",
        len(outils),
        int((time.time() - t0) * 1000),
    )
    _outils_en_memoire = outils
    return [dict(outil) for outil in outils]


def appeler_outil_mcp(nom: str, arguments: Dict[str, Any]) -> str:
    """Interface synchrone pour appeler un outil MCP.

    Args:
        nom: Le nom de l'outil, tel que le serveur l'annonce.
        arguments: Les arguments de l'appel.

    Returns:
        Le texte rendu par l'outil.

    Raises:
        ServeurMCPNonDemarre: si le serveur n'a pas démarré.
        OutilMCPEnEchec: si l'outil a rendu une erreur.
    """
    t0 = time.time()
    logger.info("Appel de l'outil MCP '%s'", nom)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(_async_appeler_outil(nom, arguments)))
            issue, texte = future.result(timeout=20.0)
    except Exception as e:
        issue, texte = ISSUE_SERVEUR, f"{type(e).__name__} : {e}"
    duree_ms = int((time.time() - t0) * 1000)

    # Le journal note l'échec et sa cause, jamais l'adresse demandée ni le texte reçu
    if issue == ISSUE_SERVEUR:
        logger.warning("Le serveur MCP n'a pas démarré pour l'outil '%s' : %s", nom, texte)
        consigner_activite(
            etape=f"mcp:{nom}",
            detail="Échec : le serveur MCP n'a pas démarré",
            duree_ms=duree_ms,
        )
        raise ServeurMCPNonDemarre(texte)

    if issue == ISSUE_OUTIL:
        logger.warning("L'outil MCP '%s' a rendu une erreur : %s", nom, texte)
        consigner_activite(
            etape=f"mcp:{nom}",
            detail=f"Échec : l'outil MCP '{nom}' a rendu une erreur",
            duree_ms=duree_ms,
        )
        raise OutilMCPEnEchec(texte)

    consigner_activite(
        etape=f"mcp:{nom}",
        detail=f"Exécution outil MCP '{nom}' terminée en {duree_ms} ms",
        duree_ms=duree_ms,
    )
    logger.info("Outil MCP '%s' terminé en %d ms", nom, duree_ms)
    return texte
