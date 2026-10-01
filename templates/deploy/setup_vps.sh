#!/usr/bin/env bash
# Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir LICENSE.md
set -e
export DEBIAN_FRONTEND=noninteractive

echo "=== 1. Mise à jour du système et installation des paquets ==="
apt update -y
apt install -y ufw unattended-upgrades curl git sqlite3 python3 python3-pip python3-venv debian-keyring debian-archive-keyring apt-transport-https

echo "=== 2. Installation de Caddy Web Server ==="
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg --yes
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update -y
apt install -y caddy

echo "=== 3. Configuration du pare-feu ufw ==="
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
echo "y" | ufw enable

echo "=== 3 bis. Connexion SSH par clé uniquement ==="
# Un serveur exposé à Internet reçoit des milliers de tentatives de connexion par jour.
# On ferme la connexion par mot de passe : seule une clé connue du serveur peut entrer.
# Le fichier est nommé 00- pour passer avant les réglages d'origine du système.
cat << 'SSHDEOF' > /etc/ssh/sshd_config.d/00-goodvibe.conf
# GoodVibe : connexion SSH par cle uniquement
PasswordAuthentication no
KbdInteractiveAuthentication no
SSHDEOF
chmod 644 /etc/ssh/sshd_config.d/00-goodvibe.conf
# sshd -t contrôle la configuration avant de la recharger : une faute ici couperait l'accès au serveur
sshd -t && systemctl reload ssh

echo "=== 4. Création de l'utilisateur {{UTILISATEUR}} ==="
if ! id -u {{UTILISATEUR}} > /dev/null 2>&1; then
    adduser --disabled-password --gecos "" {{UTILISATEUR}}
fi

# Configuration SSH pour l'utilisateur {{UTILISATEUR}}
mkdir -p /home/{{UTILISATEUR}}/.ssh
chmod 700 /home/{{UTILISATEUR}}/.ssh
cp /root/.ssh/authorized_keys /home/{{UTILISATEUR}}/.ssh/authorized_keys
chmod 600 /home/{{UTILISATEUR}}/.ssh/authorized_keys

# Génération de la clé de lecture (Deploy Key) pour GitHub
if [ ! -f /home/{{UTILISATEUR}}/.ssh/id_deploy ]; then
    ssh-keygen -t ed25519 -f /home/{{UTILISATEUR}}/.ssh/id_deploy -N "" -C "{{UTILISATEUR}}-deploy-key"
fi
chmod 600 /home/{{UTILISATEUR}}/.ssh/id_deploy
chmod 644 /home/{{UTILISATEUR}}/.ssh/id_deploy.pub

# Configuration SSH pour GitHub avec la clé de déploiement
cat << 'SSHEOF' > /home/{{UTILISATEUR}}/.ssh/config
Host github.com
    IdentityFile ~/.ssh/id_deploy
    StrictHostKeyChecking accept-new
SSHEOF
chmod 600 /home/{{UTILISATEUR}}/.ssh/config
chown -R {{UTILISATEUR}}:{{UTILISATEUR}} /home/{{UTILISATEUR}}/.ssh

# Installation de uv / uvx pour l'utilisateur {{UTILISATEUR}} (serveur MCP)
# uvx s'installe dans /home/{{UTILISATEUR}}/.local/bin. Ni le service ni le cron ne connaissent ce
# dossier : deploy/deployer.sh inscrit son chemin complet dans le .env (MCP_FETCH_COMMAND).
sudo -u {{UTILISATEUR}} bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Règle sudoers limitée
cat << 'SUDOEOF' > /etc/sudoers.d/{{UTILISATEUR}}
{{UTILISATEUR}} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart goodvibe-web, /usr/bin/systemctl restart goodvibe-web.service, /usr/bin/systemctl restart goodvibe-webhook, /usr/bin/systemctl restart goodvibe-webhook.service, /usr/bin/systemctl status goodvibe-web, /usr/bin/systemctl reload caddy
SUDOEOF
chmod 440 /etc/sudoers.d/{{UTILISATEUR}}

# Réglage du fuseau horaire : le cron suit l'heure du serveur, pas celle de la montre du pilote.
# Sans ce réglage, un serveur en heure universelle (UTC) produirait le brief à 9 h, heure de Paris, en été.
timedatectl set-timezone {{FUSEAU}}
echo "Heure du serveur : $(date)"

# Configuration de la crontab de l'utilisateur {{UTILISATEUR}} (brief à 7h, backup à 3h)
# La seule source de l'horaire est le fichier deploy/crontab : on ne le modifie jamais sur le serveur.
if [ -f /home/{{UTILISATEUR}}/app/deploy/crontab ]; then
    crontab -u {{UTILISATEUR}} /home/{{UTILISATEUR}}/app/deploy/crontab
fi

echo "=== Configuration système terminée avec succès ==="
