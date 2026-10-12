#!/usr/bin/env bash
# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
# deploy/deployer.sh - Script de déploiement automatique GoodVibe sur le VPS
# Idempotent : peut être exécuté plusieurs fois d'affilée sans effet de bord indésirable.
#
# Usage : bash deploy/deployer.sh <identifiant du commit testé>
# Le pipeline (.github/workflows/deploy.yml) passe l'identifiant du commit que ses tests
# viennent de valider. Le script installe cette version précise, jamais « la dernière de
# main » : une version poussée pendant les tests n'est pas celle qui a été validée.
set -e

COMMIT="${1:-}"
if [ -z "$COMMIT" ]; then
    echo "ERREUR : aucun identifiant de commit reçu. Le déploiement s'arrête."
    echo "Usage : bash deploy/deployer.sh <identifiant du commit testé>"
    exit 1
fi

echo "=== 1. Navigation vers le répertoire de l'application ==="
cd /home/{{NOM_AGENT}}/app

echo "=== 2. Installation de la version testée : $COMMIT ==="
# On va chercher les nouveautés, puis on se place exactement sur le commit demandé.
# Un fichier modifié à la main sur le serveur bloque toujours cette étape : rien ne se
# modifie sur le serveur, on corrige dans le dépôt, puis on déploie.
git fetch origin
git checkout --detach "$COMMIT"
INSTALLE=$(git rev-parse HEAD)
if [ "$INSTALLE" != "$(git rev-parse "$COMMIT")" ]; then
    echo "ERREUR : la version installée ($INSTALLE) n'est pas celle demandée ($COMMIT)."
    exit 1
fi

echo "=== 3. Mise à jour des dépendances dans l'environnement virtuel ==="
/home/{{NOM_AGENT}}/app/venv/bin/pip install -r requirements.txt

echo "=== 4. Actualisation de la crontab utilisateur ==="
# Toute modification dans deploy/crontab est ainsi immédiatement prise en compte
if [ -f deploy/crontab ]; then
    crontab deploy/crontab
fi

echo "=== 4 bis. Chemin complet de uvx pour le serveur MCP fetch ==="
# Ni le service ni le cron ne connaissent le dossier où uvx est installé : GoodVibe lit
# son chemin complet dans le .env (MCP_FETCH_COMMAND). On l'y inscrit s'il manque.
# Aucun contenu du .env n'est affiché.
UVX=/home/{{NOM_AGENT}}/.local/bin/uvx
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

echo "=== 4 ter. Contrôle des lignes du .env du serveur ==="
# Les deux .env (celui de l'ordinateur du pilote, celui du serveur) ont les mêmes lignes,
# pas les mêmes valeurs. .env.example est la référence : chaque ligne NOM= non commentée
# doit exister dans le .env du serveur. Seuls les noms sont comparés : aucune valeur
# n'est lue ni affichée. Une ligne absente arrêterait le service au démarrage (config.py) :
# on s'arrête ici, avant le redémarrage, et on dit laquelle.
if [ ! -f .env ]; then
    echo "ERREUR : fichier .env absent sur le serveur. Le déploiement s'arrête."
    exit 1
fi
MANQUANTES=""
for NOM in $(grep -oE '^[A-Z_]+=' .env.example | tr -d '='); do
    if ! grep -q "^${NOM}=" .env; then
        MANQUANTES="$MANQUANTES $NOM"
    fi
done
if [ -n "$MANQUANTES" ]; then
    echo "ERREUR : lignes absentes du .env du serveur :$MANQUANTES"
    echo "Ajoutez-les au .env du serveur, sans jamais recopier le .env de l'ordinateur, puis relancez le déploiement."
    exit 1
fi
echo "Toutes les lignes de .env.example sont présentes dans le .env du serveur"

echo "=== 5. Redémarrage des services de l'agent IA {{NOM_AGENT}} ==="
# Redémarrage propre sans mot de passe grâce à la règle sudoers configurée aux fiches 12 et 14
sudo systemctl restart {{NOM_AGENT}}-web
sudo systemctl restart {{NOM_AGENT}}-webhook

# L'identifiant réellement installé, à comparer avec celui affiché par le pipeline
echo "=== Déploiement terminé avec succès : version installée $(git rev-parse --short HEAD) ($INSTALLE) ==="
