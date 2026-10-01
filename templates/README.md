# Templates de référence GoodVibe

> Template GoodVibe © 2026 Jean-Noël Lefebvre (Le Cinquième Jour) — PolyForm Noncommercial 1.0.0, voir [`LICENSE.md`](../LICENSE.md) à la racine du kit.

## 1. À quoi servent ces fichiers

C'est le code de référence de GoodVibe V1 : l'état final du projet, validé en production et couvert par 140 tests automatisés. Ce n'est **pas un projet à copier**. C'est un modèle que l'agent de codage consulte fiche par fiche, pour ne jamais partir d'une page blanche et pour avoir sous les yeux une version qui marche sur les points durs (streaming, MCP, déploiement).

## 2. Les règles pour l'agent de codage

1. Au PLAN de chaque fiche, lis les fichiers de référence de la fiche (table ci-dessous) **avant** de proposer ton plan.
2. **Ne prends que ce que la fiche en cours demande.** Les références contiennent déjà les fiches suivantes : à la fiche 1, par exemple, `agent.py` n'a encore ni outils, ni mémoire, ni journal.
3. Ne copie jamais le dossier `templates/` en entier.
4. **Si le tuto et la référence divergent, le tuto prime**, et tu signales l'écart au pilote.
5. Le pilote garde la main : le PLAN, le GO et le CHECK se déroulent comme le tuto l'indique.

## 3. Fiche par fiche : les fichiers de référence

| Fiche | Fichiers |
|---|---|
| 1. Squelette et chat terminal | `config.py`, `prompt_systeme.md`, `agent.py`, `chat_terminal.py`, `requirements.txt`, `.env.example`, `.gitignore`, `.gitattributes` |
| 2. Page web | `interface.py` |
| 3. Journal d'activité | `db.py` (table `journal`), `journal.py`, `fragments.py` (1) |
| 4. Base et profil | `db.py`, `outils.py`, `agent.py`, `prompt_systeme.md`, `interface.py` |
| 5. Oublier, une note ou tout | `outils.py`, `db.py`, `prompt_systeme.md` |
| 6. Brief du matin | `brief.py`, `cron_brief.py`, `interface.py` (onglet Brief) |
| 7. Météo | `outils_meteo.py`, `outils.py` |
| 8. Horoscope via MCP | `mcp_client.py`, `horoscope.py`, `config.py` |
| 9. Onglets Mémoire et Activité | `vue_memoire.py`, `vue_activite.py`, `tarifs.py` |
| 10. Image du jour | `image.py`, `prompt_image.md` |
| 11. Tests automatisés | `tests/`, `requirements-dev.txt`, `pyproject.toml` |
| 12. Mise en ligne sur le VPS | `deploy/setup_vps.sh`, `deploy/web.service`, `deploy/site.caddy`, `deploy/crontab`, `deploy/sauvegarde.sh` |
| 13. CI/CD GitHub Actions | `.github/workflows/deploy.yml`, `deploy/deployer.sh` |
| 14. Webhook pense-bête | `webhook.py`, `deploy/webhook.service`, `db.py` (table `pense_betes`), `brief.py` |

(1) `fragments.py` n'est pas cité par le tuto. Il sépare, dans le flux du modèle, la réponse, les coulisses et le relevé, pour que seuls le message du pilote et le texte de la réponse repartent dans l'historique. Sans lui, les coulisses étaient renvoyées au modèle et la facture de tokens enflait à chaque tour.

## 4. Les marqueurs

Un serveur peut héberger plusieurs agents IA, chacun dans son « appartement » : son utilisateur Linux, son dossier, ses services, ses ports, sa fiche Caddy et son adresse. Les fichiers du serveur contiennent donc des marqueurs, à remplacer en copiant le fichier :

| Marqueur | Rôle | Premier agent IA | Deuxième agent IA |
|---|---|---|---|
| `{{NOM_AGENT}}` | Le nom de l'agent IA sur le serveur : utilisateur Linux, dossier `/home/{{NOM_AGENT}}/app`, services `{{NOM_AGENT}}-web` et `{{NOM_AGENT}}-webhook`, fiche Caddy, droits | `goodvibe` | `goodvibe2` |
| `{{PORT_WEB}}` | Le port de la page (aussi `PORT_GRADIO` dans le `.env`) | `7860` | `7861` |
| `{{PORT_WEBHOOK}}` | Le port du webhook (aussi `PORT_WEBHOOK` dans le `.env`) | `8000` | `8001` |
| `{{ADRESSE}}` | L'adresse publique, sans `https://` | `goodvibe.1-2-3-4.sslip.io` | `goodvibe2.1-2-3-4.sslip.io` |
| `{{FUSEAU}}` | Le fuseau horaire du serveur, commun à tous | `Europe/Paris` | `Europe/Paris` |

Sur le serveur, les fichiers prennent le nom de l'agent IA : `deploy/web.service` devient `/etc/systemd/system/{{NOM_AGENT}}-web.service`, `deploy/webhook.service` devient `{{NOM_AGENT}}-webhook.service`, et `deploy/site.caddy` devient `/etc/caddy/sites/{{NOM_AGENT}}.caddy`. Le `Caddyfile` principal, commun, est écrit une seule fois par `deploy/setup_vps.sh` : il lit toutes les fiches du dossier `sites/`, et n'est jamais écrasé s'il contient déjà autre chose.

**Attention** : le workflow contient aussi des `${{ … }}`, par exemple `${{ secrets.VPS_HOST }}`. Ils appartiennent à GitHub Actions : n'y touche jamais. Seuls les cinq marqueurs ci-dessus se remplacent.

Les fichiers Python ne contiennent aucun marqueur : ils tournent tels quels, et lisent leurs ports dans le `.env`.

## 5. Ce que ces fichiers ne contiennent pas, exprès

- **Aucun secret** : pas de `.env`. Les clés et mots de passe sont saisis par le pilote.
- **Aucun nom de modèle** : `MODELE_TEXTE` et `MODELE_IMAGE` sont recommandés par l'agent au PLAN des fiches 1 et 10, d'après la documentation officielle Google du jour. Sans eux, le programme s'arrête avec un message clair.
- **Aucun prix** : la grille de prix est relevée par le pilote sur la page des tarifs de Google et saisie dans l'onglet Activité.
- **Aucun document de cadrage** (`archi-stack.md`, `fdd.md`, `plan-action.md`) : le pilote les co-construit avec l'agent, c'est là qu'il apprend à cadrer.
