# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Point d'entrée du webhook sécurisé pour les pense-bêtes de GoodVibe (Feature 14).

Reçoit des messages courts envoyés depuis l'extérieur (Hoppscotch sur mobile ou navigateur,
curl.exe depuis un terminal, plus tard un raccourci ou une automatisation).
Protégé par un jeton secret dans l'en-tête X-Token.
Répond immédiatement 200 {"statut": "reçu"}, puis, en tâche de fond (BackgroundTasks),
range le pense-bête et refait le brief du jour en cycle complet, texte et image :
la recette est celle du bouton « Générer le brief maintenant » (forcer=True).
L'appelant n'attend jamais le brief : il le lit sur la page, onglet Brief.
CORS est strictement restreint à https://hoppscotch.io.
"""

import logging
from typing import Dict

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
import db
from brief import generer_brief
from journal import consigner_activite

logger = logging.getLogger(__name__)

app = FastAPI(
    title="GoodVibe Webhook",
    description="Webhook de réception des pense-bêtes",
    docs_url=None,
    redoc_url=None,
)

# Sécurité CORS : autorise uniquement les requêtes provenant de Hoppscotch
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://hoppscotch.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PenseBetePayload(BaseModel):
    """Format de données attendu pour un pense-bête reçu par webhook."""

    texte: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Contenu du pense-bête à rappeler dans le brief",
    )


def verifier_jeton(x_token: str = Header(None, alias="X-Token")) -> str:
    """Vérifie la validité du jeton secret transmis dans l'en-tête HTTP.

    Raises:
        HTTPException: 401 Unauthorized si le jeton est manquant, non configuré ou invalide.
    """
    jeton_attendu = config.WEBHOOK_TOKEN
    if not jeton_attendu or not x_token or x_token != jeton_attendu:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton d'authentification invalide ou manquant.",
        )
    return x_token


def _traiter_pense_bete_en_fond(texte: str) -> None:
    """Tâche de fond exécutée après l'envoi de la réponse 200 à l'expéditeur.

    L'ordre compte : on range d'abord le pense-bête, puis on refait le brief du jour,
    pour que ce brief le contienne. La recette est celle du bouton (forcer=True),
    texte et image : aucune variante. C'est la recette qui s'encadre dans le journal
    (ligne `brief` d'ouverture, ligne `webhook:brief` de fermeture, avec l'échec et sa
    cause le cas échéant) : ici on ne fait que passer son nom. L'appelant a déjà son
    « reçu » : en cas d'échec, le pense-bête reste non intégré, le brief suivant le
    reprendra.
    """
    db.ajouter_pense_bete(texte)
    consigner_activite("webhook", "pense-bête reçu")
    logger.info("[WEBHOOK] Pense-bête rangé, lancement du brief du jour (forcer=True)")

    try:
        generer_brief(forcer=True, declencheur="webhook")
    except Exception as e:
        # Déjà noté au journal par la recette : on empêche seulement la tâche de fond
        # de mourir en silence dans son fil d'exécution.
        logger.error("[WEBHOOK] Le brief déclenché par le webhook a échoué : %s", e)
        return
    logger.info("[WEBHOOK] Brief du jour refait après un pense-bête")


@app.post("/pense-bete", status_code=status.HTTP_200_OK)
async def recevoir_pense_bete(
    payload: PenseBetePayload,
    background_tasks: BackgroundTasks,
    _: str = Depends(verifier_jeton),
) -> Dict[str, str]:
    """Point d'entrée du webhook : valide le jeton, programme la tâche et répond aussitôt."""
    # Répondre tout de suite (200), traiter ensuite en tâche de fond
    background_tasks.add_task(_traiter_pense_bete_en_fond, payload.texte)
    return {"statut": "reçu"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=config.PORT_WEBHOOK,
        log_level="info",
    )
