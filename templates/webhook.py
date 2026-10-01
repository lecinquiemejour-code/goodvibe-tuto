# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Point d'entrée du webhook sécurisé pour les pense-bêtes de GoodVibe (Feature 14).

Reçoit des messages courts envoyés depuis l'extérieur (Hoppscotch sur mobile ou navigateur,
curl.exe depuis un terminal, plus tard un raccourci ou une automatisation).
Protégé par un jeton secret dans l'en-tête X-Token.

L'ordre compte : le jeton et le texte sont vérifiés, le pense-bête est enregistré dans
la base, puis seulement le webhook répond 202 Accepted avec le statut « enregistre »
et l'identifiant. « Enregistré » ne veut pas dire « traité » : le brief du jour est
refait ensuite, en tâche de fond (BackgroundTasks), en cycle complet, texte et image,
par la recette du bouton « Générer le brief maintenant » (forcer=True). L'appelant
n'attend jamais le brief : il le lit sur la page, onglet Brief, et le statut du
pense-bête dans l'onglet Mémoire. Si le brief échoue, le pense-bête passe en échec et
reste en base : le brief suivant le reprend, sans relance automatique.
CORS est strictement restreint à https://hoppscotch.io.
"""

import logging
from typing import Any, Dict

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


def _refaire_le_brief_en_fond(id_pense_bete: int) -> None:
    """Tâche de fond exécutée après l'envoi de la réponse 202 à l'expéditeur.

    Le pense-bête est déjà en base : le brief le contiendra. La recette est celle du
    bouton (forcer=True), texte et image : aucune variante. C'est la recette qui
    s'encadre dans le journal (ligne `brief` d'ouverture, ligne `webhook:brief` de
    fermeture, avec l'échec et sa cause le cas échéant) : ici on ne fait que passer son
    nom. Elle marque elle-même les pense-bêtes intégrés. L'appelant a déjà sa réponse :
    en cas d'échec, le pense-bête passe en échec et reste en base, le brief suivant le
    reprendra. Pas de relance automatique immédiate.
    """
    logger.info("[WEBHOOK] Lancement du brief du jour pour le pense-bête %d (forcer=True)", id_pense_bete)
    try:
        generer_brief(forcer=True, declencheur="webhook")
    except Exception as e:
        # Déjà noté au journal par la recette : on fixe le statut du pense-bête, et on
        # empêche la tâche de fond de mourir en silence dans son fil d'exécution.
        db.marquer_pense_bete_echec(id_pense_bete)
        logger.error("[WEBHOOK] Le brief déclenché par le pense-bête %d a échoué : %s", id_pense_bete, e)
        return
    logger.info("[WEBHOOK] Brief du jour refait après le pense-bête %d", id_pense_bete)


@app.post("/pense-bete", status_code=status.HTTP_202_ACCEPTED)
async def recevoir_pense_bete(
    payload: PenseBetePayload,
    background_tasks: BackgroundTasks,
    _: str = Depends(verifier_jeton),
) -> Dict[str, Any]:
    """Point d'entrée du webhook : jeton et texte vérifiés, enregistre, répond, puis traite.

    Le jeton (verifier_jeton) et le texte (PenseBetePayload) sont contrôlés avant
    d'entrer ici. Le pense-bête est écrit en base avant la réponse : si le serveur
    tombait juste après, il existerait quand même. 202 Accepted dit « enregistré,
    traitement à venir », ni plus ni moins.
    """
    id_pense_bete = db.ajouter_pense_bete(payload.texte)
    # Journal sans le texte du pense-bête
    consigner_activite("webhook", "pense-bête enregistré")
    logger.info("[WEBHOOK] Pense-bête %d enregistré, réponse 202 envoyée", id_pense_bete)
    background_tasks.add_task(_refaire_le_brief_en_fond, id_pense_bete)
    return {
        "statut": "enregistre",
        "message": db.LIBELLES_STATUT_PENSE_BETE[db.STATUT_EN_ATTENTE],
        "id": id_pense_bete,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=config.PORT_WEBHOOK,
        log_level="info",
    )
