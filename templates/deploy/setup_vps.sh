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

echo "=== 2 bis. Caddy, concierge commun : une fiche par agent IA ==="
# Plusieurs agents IA peuvent vivre sur ce serveur. Le Caddyfile principal ne contient qu'une
# ligne : lire toutes les fiches de /etc/caddy/sites/. Chaque agent IA y dépose la sienne
# (deploy/site.caddy), sans jamais toucher celle des autres.
CADDYFILE=/etc/caddy/Caddyfile
IMPORT='import /etc/caddy/sites/*.caddy'
mkdir -p /etc/caddy/sites
if grep -qxF "$IMPORT" "$CADDYFILE" 2>/dev/null; then
    echo "Caddyfile principal déjà prêt pour plusieurs agents IA : rien à changer"
elif [ ! -f "$CADDYFILE" ] || { grep -q "/usr/share/caddy" "$CADDYFILE" && ! grep -q "reverse_proxy" "$CADDYFILE"; }; then
    # Absent, ou page d'accueil livrée avec Caddy : on le remplace par le concierge commun
    cat > "$CADDYFILE" << CADDYEOF
# Caddy, concierge commun du serveur : il lit la fiche de chaque agent IA.
# Ne rien écrire d'autre ici : chaque agent IA a sa fiche dans /etc/caddy/sites/.
$IMPORT
CADDYEOF
    echo "Caddyfile principal créé"
else
    # Une configuration existe déjà (celle d'un autre agent IA ?) : on ne l'écrase jamais
    echo "ERREUR : /etc/caddy/Caddyfile contient déjà une configuration, et elle n'est pas écrasée."
    echo "Déplacez d'abord son contenu dans une fiche de /etc/caddy/sites/ (tuto, section 8.2)."
    exit 1
fi

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

echo "=== 4. Création de l'utilisateur {{NOM_AGENT}} ==="
if ! id -u {{NOM_AGENT}} > /dev/null 2>&1; then
    adduser --disabled-password --gecos "" {{NOM_AGENT}}
fi

# Configuration SSH pour l'utilisateur {{NOM_AGENT}}
mkdir -p /home/{{NOM_AGENT}}/.ssh
chmod 700 /home/{{NOM_AGENT}}/.ssh
cp /root/.ssh/authorized_keys /home/{{NOM_AGENT}}/.ssh/authorized_keys
chmod 600 /home/{{NOM_AGENT}}/.ssh/authorized_keys

# Génération de la clé de lecture (Deploy Key) pour GitHub
if [ ! -f /home/{{NOM_AGENT}}/.ssh/id_deploy ]; then
    ssh-keygen -t ed25519 -f /home/{{NOM_AGENT}}/.ssh/id_deploy -N "" -C "{{NOM_AGENT}}-deploy-key"
fi
chmod 600 /home/{{NOM_AGENT}}/.ssh/id_deploy
chmod 644 /home/{{NOM_AGENT}}/.ssh/id_deploy.pub

# Configuration SSH pour GitHub avec la clé de déploiement
cat << 'SSHEOF' > /home/{{NOM_AGENT}}/.ssh/config
Host github.com
    IdentityFile ~/.ssh/id_deploy
    StrictHostKeyChecking accept-new
SSHEOF
chmod 600 /home/{{NOM_AGENT}}/.ssh/config
chown -R {{NOM_AGENT}}:{{NOM_AGENT}} /home/{{NOM_AGENT}}/.ssh

# Installation de uv / uvx pour l'utilisateur {{NOM_AGENT}} (serveur MCP)
# uvx s'installe dans /home/{{NOM_AGENT}}/.local/bin. Ni le service ni le cron ne connaissent ce
# dossier : deploy/deployer.sh inscrit son chemin complet dans le .env (MCP_FETCH_COMMAND).
sudo -u {{NOM_AGENT}} bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

# Règle sudoers limitée
cat << 'SUDOEOF' > /etc/sudoers.d/{{NOM_AGENT}}
{{NOM_AGENT}} ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart {{NOM_AGENT}}-web, /usr/bin/systemctl restart {{NOM_AGENT}}-web.service, /usr/bin/systemctl restart {{NOM_AGENT}}-webhook, /usr/bin/systemctl restart {{NOM_AGENT}}-webhook.service, /usr/bin/systemctl status {{NOM_AGENT}}-web, /usr/bin/systemctl reload caddy
SUDOEOF
chmod 440 /etc/sudoers.d/{{NOM_AGENT}}

# Réglage du fuseau horaire : le cron suit l'heure du serveur, pas celle de la montre du pilote.
# Sans ce réglage, un serveur en heure universelle (UTC) produirait le brief à 9 h, heure de Paris, en été.
timedatectl set-timezone {{FUSEAU}}
echo "Heure du serveur : $(date)"

# Configuration de la crontab de l'utilisateur {{NOM_AGENT}} (brief à 7h, backup à 3h)
# La seule source de l'horaire est le fichier deploy/crontab : on ne le modifie jamais sur le serveur.
if [ -f /home/{{NOM_AGENT}}/app/deploy/crontab ]; then
    crontab -u {{NOM_AGENT}} /home/{{NOM_AGENT}}/app/deploy/crontab
fi

echo "=== Configuration système terminée avec succès ==="
