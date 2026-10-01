#!/usr/bin/env bash
# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
# deploy/deployer.sh - Script de déploiement automatique GoodVibe sur le VPS
# Idempotent : peut être exécuté plusieurs fois d'affilée sans effet de bord indésirable.
set -e

echo "=== 1. Navigation vers le répertoire de l'application ==="
cd /home/{{UTILISATEUR}}/app

echo "=== 2. Récupération des dernières modifications depuis GitHub ==="
git pull origin main

echo "=== 3. Mise à jour des dépendances dans l'environnement virtuel ==="
/home/{{UTILISATEUR}}/app/venv/bin/pip install -r requirements.txt

echo "=== 4. Actualisation de la crontab utilisateur ==="
# Toute modification dans deploy/crontab est ainsi immédiatement prise en compte
if [ -f deploy/crontab ]; then
    crontab deploy/crontab
fi

echo "=== 4 bis. Chemin complet de uvx pour le serveur MCP fetch ==="
# Ni le service ni le cron ne connaissent le dossier où uvx est installé : GoodVibe lit
# son chemin complet dans le .env (MCP_FETCH_COMMAND). On l'y inscrit s'il manque.
# Aucun contenu du .env n'est affiché.
UVX=/home/{{UTILISATEUR}}/.local/bin/uvx
if [ ! -x "$UVX" ]; then
    echo "ATTENTION : uvx est introuvable à $UVX. L'horoscope affichera une erreur tant qu'il n'est pas installé."
elif [ ! -f .env ]; then
    echo "ATTENTION : fichier .env absent, chemin de uvx non inscrit."
elif grep -q '^MCP_FETCH_COMMAND=' .env; then
    echo "Chemin de uvx déjà présent dans le .env"
else
    # Le fichier peut ne pas finir par un saut de ligne : on en ajoute un,
    # pour ne pas coller le nouveau réglage au dernier.
    if [ -n "$(tail -c1 .env)" ]; then
        echo >> .env
    fi
    echo "MCP_FETCH_COMMAND=$UVX" >> .env
    echo "Chemin de uvx inscrit dans le .env"
fi

echo "=== 5. Redémarrage des services GoodVibe ==="
# Redémarrage propre sans mot de passe grâce à la règle sudoers configurée aux fiches 12 et 14
sudo systemctl restart goodvibe-web
sudo systemctl restart goodvibe-webhook

echo "=== Déploiement terminé avec succès ==="
