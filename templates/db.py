# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
"""Gestionnaire de base de données SQLite pour GoodVibe.

Gère la création et l'accès aux tables locales (journal d'activité, profil, notes, conversations)
dans data/agent.db, sans serveur externe.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "agent.db"


def get_connection() -> sqlite3.Connection:
    """Retourne une connexion à la base de données SQLite locale."""
    if isinstance(DB_PATH, Path):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def initialiser() -> None:
    """Initialise le schéma de la base de données SQLite."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        # Table du journal d'activité technique (Feature 3)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                execution_id TEXT,
                agent TEXT NOT NULL DEFAULT 'goodvibe',
                etape TEXT NOT NULL,
                detail TEXT,
                tokens_entree INTEGER,
                tokens_sortie INTEGER,
                tokens_reflexion INTEGER,
                latence_ms INTEGER,
                duree_ms INTEGER
            )
            """
        )

        # Table du profil utilisateur (Feature 4)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profil (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prenom TEXT,
                signe TEXT,
                ville TEXT,
                interets TEXT,
                maj TEXT NOT NULL
            )
            """
        )

        # Table des notes et mémos (Feature 4)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                texte TEXT NOT NULL
            )
            """
        )

        # Table des conversations persistées (Feature 4)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session TEXT NOT NULL DEFAULT 'default',
                role TEXT NOT NULL,
                contenu TEXT NOT NULL,
                date TEXT NOT NULL
            )
            """
        )

        # Table des briefs générés (Feature 6)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS briefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                contenu TEXT NOT NULL,
                cree_le TEXT NOT NULL
            )
            """
        )

        # Table des clés traitées / anti-doublon (Feature 6)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traites (
                cle TEXT PRIMARY KEY,
                date_traitement TEXT NOT NULL
            )
            """
        )

        # Table des tarifs configurables en USD (Feature 9)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tarifs (
                id INTEGER PRIMARY KEY,
                prix_entree_usd REAL NOT NULL,
                prix_sortie_usd REAL NOT NULL,
                prix_reflexion_usd REAL NOT NULL,
                prix_image_usd REAL NOT NULL,
                maj TEXT NOT NULL
            )
            """
        )

        # Table des pense-bêtes reçus par webhook (Feature 14)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pense_betes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                texte TEXT NOT NULL,
                integre INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # La table démarre vide : aucun prix n'est écrit d'avance dans le code. C'est le pilote
        # qui relève les prix de ses modèles sur la page de Google et les saisit dans l'onglet Activité.
        conn.commit()


# Fonctions d'accès aux tarifs configurables (Feature 9)

def get_tarifs() -> Optional[Dict[str, Any]]:
    """Récupère la grille tarifaire active en USD stockée en base SQLite.

    Returns:
        La grille saisie par le pilote, ou None tant qu'il n'en a saisi aucune :
        aucun prix par défaut ne la remplace.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT prix_entree_usd, prix_sortie_usd, prix_reflexion_usd, prix_image_usd, maj
            FROM tarifs WHERE id = 1
            """
        )
        row = cursor.fetchone()
        if row:
            return {
                "prix_entree_usd": float(row["prix_entree_usd"]),
                "prix_sortie_usd": float(row["prix_sortie_usd"]),
                "prix_reflexion_usd": float(row["prix_reflexion_usd"]),
                "prix_image_usd": float(row["prix_image_usd"]),
                "maj": row["maj"],
            }
        return None


def sauvegarder_tarifs(
    prix_entree_usd: float,
    prix_sortie_usd: float,
    prix_reflexion_usd: float,
    prix_image_usd: float,
) -> None:
    """Enregistre la grille tarifaire en USD saisie par le pilote (les quatre prix sont obligatoires)."""
    maintenant = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO tarifs (id, prix_entree_usd, prix_sortie_usd, prix_reflexion_usd, prix_image_usd, maj)
            VALUES (1, ?, ?, ?, ?, ?)
            """,
            (prix_entree_usd, prix_sortie_usd, prix_reflexion_usd, prix_image_usd, maintenant),
        )
        conn.commit()




# Fonctions d'accès au profil utilisateur

def get_profil() -> Optional[Dict[str, Any]]:
    """Récupère les informations du profil utilisateur s'il existe."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, prenom, signe, ville, interets, maj FROM profil ORDER BY id LIMIT 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def sauvegarder_profil(
    prenom: Optional[str] = None,
    ville: Optional[str] = None,
    interets: Optional[str] = None,
    signe: Optional[str] = None,
) -> None:
    """Met à jour ou insère les informations du profil en base locale."""
    maintenant = datetime.now(timezone.utc).isoformat()
    profil_existant = get_profil()

    with get_connection() as conn:
        if profil_existant:
            # Mise à jour partielle des champs fournis
            nouveau_prenom = prenom if prenom is not None else profil_existant.get("prenom")
            nouvelle_ville = ville if ville is not None else profil_existant.get("ville")
            nouveaux_interets = interets if interets is not None else profil_existant.get("interets")
            nouveau_signe = signe if signe is not None else profil_existant.get("signe")

            conn.execute(
                """
                UPDATE profil
                SET prenom = ?, ville = ?, interets = ?, signe = ?, maj = ?
                WHERE id = ?
                """,
                (nouveau_prenom, nouvelle_ville, nouveaux_interets, nouveau_signe, maintenant, profil_existant["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO profil (prenom, ville, interets, signe, maj)
                VALUES (?, ?, ?, ?, ?)
                """,
                (prenom, ville, interets, signe, maintenant),
            )
        conn.commit()


# Fonctions d'accès aux notes et mémos

def ajouter_note(texte: str) -> int:
    """Enregistre une nouvelle note avec horodatage UTC."""
    maintenant = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO notes (date, texte) VALUES (?, ?)",
            (maintenant, texte.strip()),
        )
        conn.commit()
        return cursor.lastrowid


def get_notes(limite: Optional[int] = None) -> List[Dict[str, Any]]:
    """Récupère les notes enregistrées (toutes les notes si limite est None)."""
    with get_connection() as conn:
        if limite is not None:
            cursor = conn.execute(
                "SELECT id, date, texte FROM notes ORDER BY id DESC LIMIT ?",
                (limite,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, date, texte FROM notes ORDER BY id DESC"
            )
        return [dict(row) for row in cursor.fetchall()]


def supprimer_note(id_note: int) -> bool:
    """Supprime une note par son identifiant unique.

    Returns:
        True si la note a été trouvée et supprimée, False sinon.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM notes WHERE id = ?", (id_note,))
        conn.commit()
        return cursor.rowcount > 0


# Fonctions d'accès aux pense-bêtes reçus par webhook (Feature 14)

def ajouter_pense_bete(texte: str) -> int:
    """Enregistre un pense-bête reçu par webhook avec horodatage UTC.

    Initialement non intégré dans le brief (integre = 0).
    """
    maintenant = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO pense_betes (date, texte, integre) VALUES (?, ?, 0)",
            (maintenant, texte.strip()),
        )
        conn.commit()
        return cursor.lastrowid


def get_pense_betes(non_integres_seulement: bool = False) -> List[Dict[str, Any]]:
    """Récupère les pense-bêtes enregistrés.

    Args:
        non_integres_seulement: Si True, ne renvoie que les pense-bêtes en attente
            d'intégration dans un brief (integre == 0), par ordre chronologique.
            Si False, renvoie tous les pense-bêtes par ordre antéchronologique.
    """
    with get_connection() as conn:
        if non_integres_seulement:
            cursor = conn.execute(
                "SELECT id, date, texte, integre FROM pense_betes WHERE integre = 0 ORDER BY id ASC"
            )
        else:
            cursor = conn.execute(
                "SELECT id, date, texte, integre FROM pense_betes ORDER BY id DESC"
            )
        return [dict(row) for row in cursor.fetchall()]


def marquer_pense_betes_integres(ids: List[int]) -> None:
    """Marque une liste de pense-bêtes comme intégrés dans un brief (integre = 1)."""
    if not ids:
        return
    with get_connection() as conn:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE pense_betes SET integre = 1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()


def supprimer_pense_bete(id_pense_bete: int) -> bool:
    """Supprime un pense-bête par son identifiant unique.

    Returns:
        True si le pense-bête a été trouvé et supprimé, False sinon.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM pense_betes WHERE id = ?", (id_pense_bete,))
        conn.commit()
        return cursor.rowcount > 0



# Fonctions d'accès à l'historique des conversations

_IGNORER_SAUVEGARDE_ECHANGE = False


def marquer_oubli_actif(actif: bool = True) -> None:
    """Demande d'ignorer l'échange en cours à la sauvegarde.

    Réservé à l'effacement demandé dans le chat : l'échange qui contient la demande
    d'oubli ne doit pas être enregistré juste après l'effacement. Le bouton de la
    page n'arme pas ce verrou : aucun échange n'est en cours quand on clique.
    """
    global _IGNORER_SAUVEGARDE_ECHANGE
    _IGNORER_SAUVEGARDE_ECHANGE = actif


def oubli_en_cours() -> bool:
    """Indique si un effacement vient d'avoir lieu au milieu de l'échange en cours."""
    return _IGNORER_SAUVEGARDE_ECHANGE


def sauvegarder_message(role: str, contenu: str, session: str = "default") -> None:
    """Enregistre un message dans la table conversations."""
    global _IGNORER_SAUVEGARDE_ECHANGE
    if _IGNORER_SAUVEGARDE_ECHANGE:
        if role == "assistant":
            # Fin du tour d'effacement : on réactive la persistance pour les prochains échanges
            _IGNORER_SAUVEGARDE_ECHANGE = False
        return

    maintenant = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversations (session, role, contenu, date)
            VALUES (?, ?, ?, ?)
            """,
            (session, role, contenu, maintenant),
        )
        conn.commit()


def charger_historique(session: str = "default", limite: int = 50) -> List[Dict[str, str]]:
    """Charge les derniers messages de la session dans l'ordre chronologique."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT role, contenu
            FROM (
                SELECT id, role, contenu
                FROM conversations
                WHERE session = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (session, limite),
        )
        return [{"role": row["role"], "content": row["contenu"]} for row in cursor.fetchall()]


def effacer_donnees_utilisateur() -> None:
    """Efface toutes les données privées de l'utilisateur (profil, notes, conversations, pense-bêtes).

    Conserve intacte la table journal qui contient uniquement les métriques techniques.
    N'arme pas le verrou de sauvegarde : c'est à l'appelant de le faire s'il efface
    au milieu d'un échange (voir marquer_oubli_actif).
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM profil")
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM conversations")
        conn.execute("DELETE FROM pense_betes")
        conn.commit()


# Fonctions d'accès aux briefs et verrous anti-doublon (Feature 6)

def sauvegarder_brief(contenu: str, date_jour: Optional[str] = None) -> int:
    """Enregistre un brief généré dans la table briefs."""
    if date_jour is None:
        date_jour = datetime.now().strftime("%Y-%m-%d")
    maintenant = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO briefs (date, contenu, cree_le) VALUES (?, ?, ?)",
                (date_jour, contenu.strip(), maintenant),
            )
            return cursor.lastrowid
    finally:
        conn.close()


def get_dernier_brief() -> Optional[Dict[str, Any]]:
    """Récupère le dernier brief enregistré."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, date, contenu, cree_le FROM briefs ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def est_deja_traite(cle: str) -> bool:
    """Vérifie si une clé de traitement existe dans la table traites."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT 1 FROM traites WHERE cle = ?",
            (cle,),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def marquer_traite(cle: str) -> None:
    """Enregistre ou met à jour une clé de traitement dans la table traites."""
    maintenant = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO traites (cle, date_traitement) VALUES (?, ?)",
                (cle, maintenant),
            )
    finally:
        conn.close()


# Initialisation automatique dès l'importation du module
initialiser()


