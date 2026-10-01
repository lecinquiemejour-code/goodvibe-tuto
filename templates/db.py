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

# Les trois états d'un pense-bête reçu par webhook (Feature 14). « Enregistré » ne veut
# pas dire « traité » : le brief qui l'intègre vient après, et peut échouer.
STATUT_EN_ATTENTE = "en_attente"
STATUT_INTEGRE = "integre"
STATUT_ECHEC = "echec"

# Ce que l'utilisateur lit pour chaque état, dans la réponse du webhook et l'onglet Mémoire
LIBELLES_STATUT_PENSE_BETE = {
    STATUT_EN_ATTENTE: "Pense-bête enregistré. Génération du brief en attente.",
    STATUT_INTEGRE: "Pense-bête intégré au brief.",
    STATUT_ECHEC: "Pense-bête enregistré, mais la préparation du brief a échoué.",
}


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
                statut TEXT NOT NULL DEFAULT 'en_attente'
            )
            """
        )
        _migrer_statut_pense_betes(conn)
        # La table démarre vide : aucun prix n'est écrit d'avance dans le code. C'est le pilote
        # qui relève les prix de ses modèles sur la page de Google et les saisit dans l'onglet Activité.
        conn.commit()


def _migrer_statut_pense_betes(conn: sqlite3.Connection) -> None:
    """Ajoute la colonne statut aux bases créées avant elle, et y recopie l'ancien oui/non.

    CREATE TABLE IF NOT EXISTS ne touche pas une table qui existe déjà : sur le serveur,
    la base garde l'ancienne colonne integre (0 ou 1). On ajoute statut, et chaque
    pense-bête déjà intégré le reste. L'ancienne colonne n'est plus lue.
    """
    colonnes = [ligne["name"] for ligne in conn.execute("PRAGMA table_info(pense_betes)").fetchall()]
    if "statut" in colonnes:
        return
    conn.execute("ALTER TABLE pense_betes ADD COLUMN statut TEXT NOT NULL DEFAULT 'en_attente'")
    if "integre" in colonnes:
        conn.execute("UPDATE pense_betes SET statut = ? WHERE integre = 1", (STATUT_INTEGRE,))


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

    Il démarre « en attente » : le brief qui l'intègre vient après.

    Returns:
        L'identifiant du pense-bête, rendu à l'appelant du webhook.
    """
    maintenant = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO pense_betes (date, texte, statut) VALUES (?, ?, ?)",
            (maintenant, texte.strip(), STATUT_EN_ATTENTE),
        )
        conn.commit()
        return cursor.lastrowid


def get_pense_betes(non_integres_seulement: bool = False) -> List[Dict[str, Any]]:
    """Récupère les pense-bêtes enregistrés.

    Args:
        non_integres_seulement: Si True, ne renvoie que les pense-bêtes que le prochain
            brief doit reprendre (en attente, ou en échec), par ordre chronologique.
            Si False, renvoie tous les pense-bêtes par ordre antéchronologique.
    """
    with get_connection() as conn:
        if non_integres_seulement:
            cursor = conn.execute(
                "SELECT id, date, texte, statut FROM pense_betes WHERE statut != ? ORDER BY id ASC",
                (STATUT_INTEGRE,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, date, texte, statut FROM pense_betes ORDER BY id DESC"
            )
        return [dict(row) for row in cursor.fetchall()]


def marquer_pense_betes_integres(ids: List[int]) -> None:
    """Marque une liste de pense-bêtes comme intégrés dans un brief."""
    if not ids:
        return
    with get_connection() as conn:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE pense_betes SET statut = ? WHERE id IN ({placeholders})",
            [STATUT_INTEGRE, *ids],
        )
        conn.commit()


def marquer_pense_bete_echec(id_pense_bete: int) -> None:
    """Note que le brief déclenché par ce pense-bête a échoué.

    Le pense-bête reste en base : le prochain brief le reprendra. Un pense-bête déjà
    intégré n'est pas touché.
    """
    with get_connection() as conn:
        conn.execute(
            "UPDATE pense_betes SET statut = ? WHERE id = ? AND statut != ?",
            (STATUT_ECHEC, id_pense_bete, STATUT_INTEGRE),
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

def sauvegarder_message(role: str, contenu: str, session: str = "default") -> None:
    """Enregistre un message dans la table conversations."""
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
    """Efface, dans la base, toutes les données de l'utilisateur et ce qui en a été tiré.

    Les tables profil, notes, conversations et pense-bêtes, mais aussi les briefs, qui
    citent le prénom, la ville et l'horoscope, et les verrous anti-doublon du jour
    (brief:date, image-date), traces que des briefs ont existé. Supprimer une donnée
    de sa table principale ne suffit pas : ses copies partent avec elle.

    Conserve intacte la table journal, qui ne contient que des mesures techniques, et
    la grille de prix. Les images sur le disque sont retirées par image.py ; l'ensemble
    est orchestré par oubli.py, appelé sur un geste de l'utilisateur seulement.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM profil")
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM conversations")
        conn.execute("DELETE FROM pense_betes")
        conn.execute("DELETE FROM briefs")
        conn.execute("DELETE FROM traites WHERE cle LIKE 'brief:%' OR cle LIKE 'image-%'")
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


