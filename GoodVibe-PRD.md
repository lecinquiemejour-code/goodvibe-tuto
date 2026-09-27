# PRD — GoodVibe

> **Version** 1.0 · **Date** 27 septembre 2026 · **Auteur** Le Cinquième Jour (tuto « Agent Python, webhook et cron en vibe coding ») · **Statut** Validé (fourni prêt à l'emploi pour le parcours pédagogique)

> Ce PRD est **fourni par le tuto**. Copiez-le tel quel à la racine de votre projet sous le nom `GoodVibe-PRD.md` (ou `PRD.md` si votre agent ne le retrouve pas), à côté du tuto `tuto-goodvibe-vibecoding.md` qui sert de référence à l'agent, puis lancez le skill VibeCoding Copilote. Il décrit le **quoi**, jamais le **comment** : c'est le skill qui vous proposera l'architecture et le découpage.

## 1. Vision & Objectifs

GoodVibe est un assistant personnel du matin : il apprend qui vous êtes en discutant avec vous, prépare chaque jour un brief personnalisé (horoscope réécrit pour vous, image du jour, météo de votre ville, pense-bêtes), et répond à vos questions dans la journée depuis votre terminal ou une page web privée.

**Objectifs :**
- Servir de fil rouge à l'apprentissage des agents autonomes : un seul projet qui gagne, feature après feature, un déclencheur (chat, cron, webhook), une mémoire, un outil MCP et une observabilité complète.
- Être un vrai produit en production sur un VPS, mis à jour par un pipeline GitHub Actions, avant d'évoluer en version 2 vers une architecture à sous-agents.
- Rendre visible ce que fait et ce que sait l'agent : tout ce qu'il mémorise et chaque décision qu'il prend doivent pouvoir être observés par le pilote.

## 2. Non-objectifs

Ce que ce produit ne cherche **pas** à être :
- Un service multi-utilisateurs : GoodVibe sert une seule personne.
- Une application d'astrologie sérieuse : l'horoscope est un prétexte ludique.
- Un système de notification : pas d'envoi de mail, de SMS ni de message instantané.
- Un moteur de recherche dans sa mémoire : pas de recherche sémantique ni de RAG.

## 3. Utilisateurs cibles

| Persona | Caractéristiques | Besoin principal |
|---------|------------------|------------------|
| Le pilote (stagiaire du bootcamp) | Code déjà, découvre les agents et le vibe coding, dispose d'Antigravity et d'une clé Gemini | Construire un agent complet en comprenant chaque brique, et pouvoir observer ce que l'agent fait et sait |
| L'utilisateur de GoodVibe (souvent la même personne, avec un profil fictif) | Utilise un navigateur et un téléphone | Recevoir un brief du matin personnalisé et pouvoir discuter avec l'assistant |

## 4. Fonctionnalités (MoSCoW)

- **Must have** :
  - Discuter avec l'utilisateur dans le terminal, réponses affichées en streaming (mot à mot).
  - Retenir le profil donné en conversation : prénom, date de naissance (dont on déduit le signe astrologique), ville de résidence, centres d'intérêt.
  - Restituer ce que l'agent sait de l'utilisateur sur demande (« qu'est-ce que tu sais de moi ? »).
  - Oublier complètement l'utilisateur sur demande (profil, notes, conversations), avec confirmation.
  - Produire chaque matin à 7 h un brief : horoscope du jour personnalisé (réécrit pour l'utilisateur à partir d'une source externe) et météo de sa ville.
  - Ne produire qu'un brief par jour, même si le déclencheur s'exécute plusieurs fois.
  - Déclencher la génération du brief à la main depuis la page web (bouton « Générer le brief maintenant »), pour tester sans attendre le cron.
  - Recevoir un pense-bête par webhook sécurisé (jeton secret) et l'intégrer au brief suivant.
  - Lire le brief du jour et discuter avec l'agent dans une page web protégée par mot de passe.
  - Afficher dans la page web le contenu de la mémoire de l'agent (profil, notes, conversations, éléments traités), avec un bouton « Oublie-moi ».
  - Afficher dans la page web le journal d'activité de l'agent : pour chaque exécution, les outils appelés, les tokens consommés (entrée, sortie, réflexion), la latence de chaque appel, avec compteurs par jour et cumul et une estimation du coût en euros.
  - Enregistrer, pour chaque réponse en conversation, le temps avant le premier mot et la durée totale.
  - Permettre d'afficher ou de masquer le résumé de réflexion (« thinking ») du modèle avant chaque réponse, via une case à cocher dans la page web et une commande dans le terminal.
- **Should have** :
  - Générer une image du jour inspirée de trois éléments : la météo du jour, le lieu de résidence et la prévision d'horoscope ; l'afficher au-dessus du brief et sur demande dans le chat.
  - Expliquer dans le chat ce que l'agent vient de faire, outil par outil, à partir de son journal.
  - Respecter un budget quotidien de tokens ; au-delà, passer en mode économe (pas d'image, réponses courtes, réflexion réduite) sans jamais empêcher le brief de sortir.
- **Could have** :
  - Envoyer le pense-bête depuis le téléphone via un raccourci (Raccourcis iOS, HTTP Shortcuts Android).
  - Version 2 : déléguer l'horoscope et la météo à des sous-agents spécialisés, avec comparaison mesurée V1 / V2 (tokens, latence, comportement en panne).
- **Won't have (pour l'instant)** :
  - Plusieurs utilisateurs, notifications sortantes, recherche sémantique dans la mémoire, chiffrement de la base au repos, authentification à deux facteurs.

## 5. Interactions

- L'utilisateur se présente en conversation (« Je m'appelle Marc, né le 12 mars 1988, j'habite Lyon, j'aime le vélo ») → l'agent enregistre le profil, calcule le signe, confirme en une phrase.
- L'utilisateur demande « qu'est-ce que tu sais de moi ? » → l'agent liste prénom, signe, ville, centres d'intérêt et notes, avec ses mots.
- L'utilisateur dit « oublie-moi » → l'agent demande confirmation, puis efface profil, notes et conversations, et confirme.
- Il est 7 h → le brief du jour est généré et enregistré ; s'il existe déjà, rien n'est refait et le journal le mentionne.
- L'utilisateur clique « Générer le brief maintenant » → même génération, immédiate, avec l'anti-doublon contournable pour les tests.
- Un service externe envoie un pense-bête sur le webhook avec le bon jeton → réponse immédiate « reçu », enregistrement, intégration au brief suivant. Sans jeton ou avec un mauvais jeton → refus.
- L'utilisateur ouvre la page web → mot de passe demandé ; puis onglets Chat, Brief du jour, Mémoire, Activité.
- L'utilisateur coche « Voir la réflexion » → un bloc grisé et repliable montre le résumé de raisonnement du modèle avant chaque réponse.
- L'utilisateur demande « explique ce que tu viens de faire » → l'agent raconte son dernier tour, outil par outil, à partir du journal.
- Une API externe ne répond pas → le brief sort quand même, avec un texte de repli, et le journal note l'échec.

## 6. Spécifications visuelles / d'interface

- **Apparence :** sobre et lisible, page web en quatre onglets (Chat, Brief du jour, Mémoire, Activité). L'image du jour, si présente, s'affiche au-dessus du texte du brief. Les tableaux de la mémoire et du journal sont bruts et complets : c'est une vitrine pédagogique, pas une interface grand public.
- **Comportement :** le chat affiche les réponses mot à mot ; les onglets Mémoire et Activité ont un bouton « Rafraîchir » ; le résumé de réflexion est replié par défaut ; un interrupteur « détails techniques » dans l'onglet Activité ajoute arguments d'outils, durées et erreurs brutes.

## 7. Contraintes (exigences non-fonctionnelles)

- **Technique :** Python 3.12 ; SDK `google-genai` (API Interactions, modèle texte `gemini-3.8-flash`, modèle image `gemini-3.1-flash-lite-image`) ; FastAPI + uvicorn pour le webhook ; Gradio pour la page web ; SQLite pour la base ; bibliothèque `mcp` comme client MCP ; `logging` de la bibliothèque standard ; `httpx` pour les appels HTTP. Code modulaire, un fichier par responsabilité. Aucun secret dans le code : tout en variables d'environnement.
- **Déploiement :** VPS Ubuntu LTS, services `systemd`, Caddy en reverse proxy HTTPS, déploiement automatique par GitHub Actions à chaque push sur `main`. **La mise en ligne se fait sur ce VPS, pas sur Netlify.**
- **Données :** un seul utilisateur, profil fictif recommandé pour la démo. Jamais de donnée personnelle dans les logs, le journal, les tests ni le dépôt Git. Minimisation : le signe suffit, la date de naissance complète n'est pas conservée après calcul. Effacement complet sur demande.
- **Observabilité :** chaque appel au modèle ou à un outil enregistre tokens (entrée, sortie, réflexion), latence et durée, sans donnée personnelle.
- **Qualité :** au moins un test automatisé par fonctionnalité, exécuté par la CI, sans appel réseau réel. Nombre maximal de tours par exécution de l'agent. Texte de repli si une API externe échoue. Budget quotidien de tokens.
- **Performance :** premier mot affiché en moins de 3 secondes en conversation dans les conditions normales de l'API ; brief généré en moins de 60 secondes.
- **Compatibilité :** page web utilisable sur un navigateur de bureau récent ; lisible sur mobile sans être optimisée.
- **Accessibilité :** contrastes suffisants, aucune information portée par la couleur seule.

## 8. Critères de succès

- Le pilote peut, depuis la page web, lire un brief du jour contenant horoscope personnalisé et météo, et voir dans l'onglet Activité les appels et les tokens qui l'ont produit.
- Un second lancement du cron le même jour ne produit pas de second brief, et le journal le dit.
- Un pense-bête envoyé par webhook avec le bon jeton apparaît dans le brief suivant ; sans jeton, la requête est refusée.
- Après « oublie-moi », l'onglet Mémoire est vide et l'agent ne sait plus rien de l'utilisateur.
- Un push sur `main` déclenche le pipeline, la coche verte apparaît, et la page publique reflète le changement sans intervention manuelle sur le VPS.
- Aucune donnée personnelle n'apparaît dans les logs ni dans le dépôt.

## 9. Hypothèses & Questions ouvertes

- **Hypothèses retenues :** la source d'horoscope est une API publique gratuite en anglais (freehoroscopeapi.com), lue via le serveur MCP officiel `fetch`, avec un plan B local si elle ne répond pas ; la météo vient d'Open-Meteo (sans clé) ; l'utilisateur unique est identifié par la session, sans compte.
- **À trancher plus tard :** aucune pour la version 1. La version 2 (sous-agents) sera cadrée dans un second cycle à partir de la section « Pour aller plus loin » du plan d'action.
