# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Module d'observabilité et de journalisation de GoodVibe.

Propose un handler de logging personnalisé qui enregistre les événements
à la fois dans la console et dans la table SQLite 'journal'.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db import get_connection


class SQLiteJournalHandler(logging.Handler):
    """Handler de logging qui insère chaque log structuré dans la table SQLite journal."""

    def emit(self, record: logging.LogRecord) -> None:
        if not getattr(record, "consigner_journal", False):
            return

        date_iso = datetime.now(timezone.utc).isoformat()
        execution_id = getattr(record, "execution_id", None)
        agent_nom = getattr(record, "agent_nom", "goodvibe")
        etape = getattr(record, "etape", record.funcName or "action")
        detail = record.getMessage()
        tokens_entree = getattr(record, "tokens_entree", None)
        tokens_sortie = getattr(record, "tokens_sortie", None)
        tokens_reflexion = getattr(record, "tokens_reflexion", None)
        latence_ms = getattr(record, "latence_ms", None)
        duree_ms = getattr(record, "duree_ms", None)

        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO journal (
                        date, execution_id, agent, etape, detail,
                        tokens_entree, tokens_sortie, tokens_reflexion,
                        latence_ms, duree_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        date_iso,
                        execution_id,
                        agent_nom,
                        etape,
                        detail,
                        tokens_entree,
                        tokens_sortie,
                        tokens_reflexion,
                        latence_ms,
                        duree_ms,
                    ),
                )
                conn.commit()
        except Exception:
            self.handleError(record)


# Configuration du logger dédié au journal GoodVibe
logger = logging.getLogger("goodvibe.journal")
logger.setLevel(logging.INFO)

# Évite les doublons de handler
if not any(isinstance(h, SQLiteJournalHandler) for h in logger.handlers):
    logger.addHandler(SQLiteJournalHandler())


def consigner_activite(
    etape: str,
    detail: str,
    execution_id: Optional[str] = None,
    tokens_entree: Optional[int] = None,
    tokens_sortie: Optional[int] = None,
    tokens_reflexion: Optional[int] = None,
    latence_ms: Optional[int] = None,
    duree_ms: Optional[int] = None,
) -> None:
    """Enregistre une activité technique dans le journal (console + base SQLite).

    Garantit l'absence de donnée personnelle dans le détail consigné.
    """
    extra = {
        "consigner_journal": True,
        "execution_id": execution_id or str(uuid.uuid4())[:8],
        "agent_nom": "goodvibe",
        "etape": etape,
        "tokens_entree": tokens_entree,
        "tokens_sortie": tokens_sortie,
        "tokens_reflexion": tokens_reflexion,
        "latence_ms": latence_ms,
        "duree_ms": duree_ms,
    }
    logger.info(detail, extra=extra)


def get_dernieres_activites(limite: int = 20) -> List[Dict[str, Any]]:
    """Récupère les dernières lignes du journal pour affichage ou explication."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, date, execution_id, etape, detail,
                   tokens_entree, tokens_sortie, tokens_reflexion,
                   latence_ms, duree_ms
            FROM journal
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        )
        return [dict(row) for row in cursor.fetchall()]


def lire_journal_execution(
    execution_id: Optional[str] = None, limite: int = 15
) -> List[Dict[str, Any]]:
    """Récupère les événements du journal pour une exécution donnée (ou la dernière)."""
    with get_connection() as conn:
        cible_id = execution_id
        if not cible_id:
            cursor_last = conn.execute(
                """
                SELECT execution_id FROM journal
                WHERE execution_id IS NOT NULL AND execution_id != ''
                ORDER BY id DESC LIMIT 1
                """
            )
            row_last = cursor_last.fetchone()
            if not row_last:
                return []
            cible_id = row_last["execution_id"]

        cursor = conn.execute(
            """
            SELECT id, date, execution_id, agent, etape, detail,
                   tokens_entree, tokens_sortie, tokens_reflexion,
                   latence_ms, duree_ms
            FROM journal
            WHERE execution_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (cible_id, limite),
        )
        return [dict(row) for row in cursor.fetchall()]
