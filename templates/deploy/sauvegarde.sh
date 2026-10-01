#!/usr/bin/env bash
# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
# Script de sauvegarde nocturne de la base SQLite GoodVibe (Feature 12)
# Exécuté chaque nuit à 3h00 par la crontab de l'utilisateur {{UTILISATEUR}}

set -euo pipefail
cd /home/{{UTILISATEUR}}

DATE=$(date +"%Y%m%d_%H%M%S")
APP_DIR="/home/{{UTILISATEUR}}/app"
BACKUP_DIR="/home/{{UTILISATEUR}}/backups"
DB_SRC="$APP_DIR/data/agent.db"
DB_DEST="$BACKUP_DIR/agent_${DATE}.db"

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_SRC" ]; then
    # Sauvegarde SQLite à chaud et atomique sans bloquer les écritures
    sqlite3 "$DB_SRC" ".backup '$DB_DEST'"
    chmod 600 "$DB_DEST"
    echo "[$(date)] Sauvegarde réussie : $DB_DEST"
    
    # Rétention : conserve les sauvegardes des 7 derniers jours
    find "$BACKUP_DIR" -name "agent_*.db" -type f -mtime +7 -delete
else
    echo "[$(date)] Aucune base de données trouvée à sauvegarder dans $DB_SRC"
fi
