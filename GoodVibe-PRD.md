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
  - Retirer une note précise sur demande, avec confirmation, sans toucher au reste de la mémoire.
  - Oublier complètement l'utilisateur sur demande (profil, notes, pense-bêtes reçus, conversations), avec confirmation.
  - Produire chaque matin à 7 h un brief : horoscope du jour personnalisé (réécrit pour l'utilisateur à partir d'une source externe) et météo de sa ville.
  - Ouvrir le brief par le jour de la semaine, la date et l'heure de sa création, lus sur l'horloge de la machine : le modèle ne les devine jamais.
  - S'adresser à l'utilisateur, dans le brief comme dans le chat, avec le prénom, la ville et le signe lus dans la mémoire au moment de répondre. L'agent n'invente jamais une information de profil : si le prénom manque, il ne salue personne par son nom et invite l'utilisateur à se présenter.
  - Ne produire qu'un brief par jour, même si le déclencheur s'exécute plusieurs fois.
  - Déclencher la génération du brief à la main depuis la page web (bouton « Générer le brief maintenant »), pour tester sans attendre le cron.
  - Recevoir un pense-bête par webhook sécurisé (jeton secret) et l'intégrer au brief suivant.
  - Lire le brief du jour et discuter avec l'agent dans une page web protégée par mot de passe.
  - Se déconnecter de la page web par un bouton visible depuis tous les onglets.
  - Afficher dans la page web le contenu de la mémoire de l'agent (profil, notes, conversations), avec un bouton « Oublie-moi ».
  - Afficher dans la page web le journal d'activité de l'agent : pour chaque exécution, les outils appelés, les tokens consommés (entrée, sortie, réflexion), la latence de chaque appel, avec compteurs par jour et cumul et une estimation du coût en euros.
  - Enregistrer, pour chaque réponse en conversation, le temps avant le premier mot et la durée totale.
  - Permettre d'afficher ou de masquer les coulisses de chaque réponse, via une case à cocher dans la page web et une commande dans le terminal : le résumé de réflexion (« thinking ») du modèle, puis chaque appel d'outil avec son nom, le JSON de ses arguments et le JSON de son résultat. L'affichage est le même pour tous les outils : fonctions Python, serveurs MCP actuels et futurs. Les coulisses s'affichent à l'écran ; les arguments et les résultats des outils ne sont jamais enregistrés dans le journal. Les coulisses et le relevé ne sont ni enregistrés dans les conversations, ni renvoyés au modèle : la mémoire de conversation et l'historique ne contiennent que le dialogue, c'est-à-dire les messages de l'utilisateur et le texte des réponses.
  - Montrer en direct le travail de l'agent chaque fois que l'utilisateur le déclenche, dans le chat comme dans la génération du brief. Dans l'ordre : chaque appel d'outil avec son nom, ses JSON et sa durée ; le résumé de réflexion du modèle, au fil de l'eau ; la réponse, mot à mot ; puis un relevé : tokens d'entrée, de réflexion et de sortie, nombre de tours, temps avant le premier mot, durée totale. Les chiffres du relevé sont ceux que renvoie l'API, jamais une estimation ; les tokens sont additionnés sur tous les tours de la réponse. Déclenché par le cron, l'agent travaille en silence : seul le journal en garde la trace, sans donnée personnelle.
- **Should have** :
  - Générer une image du jour inspirée de quatre éléments : la météo du jour, le lieu de résidence, la prévision d'horoscope et les centres d'intérêt de l'utilisateur ; l'afficher au-dessus du brief et sur demande dans le chat.
  - Expliquer dans le chat ce que l'agent vient de faire, outil par outil, à partir de son journal.
- **Could have** :
  - Envoyer le pense-bête depuis le téléphone via un raccourci (Raccourcis iOS, HTTP Shortcuts Android).
  - Version 2 : déléguer l'horoscope et la météo à des sous-agents spécialisés, avec comparaison mesurée V1 / V2 (tokens, latence, comportement en panne).
- **Won't have (pour l'instant)** :
  - Budget quotidien de tokens et mode économe, plusieurs utilisateurs, notifications sortantes, recherche sémantique dans la mémoire, chiffrement de la base au repos, authentification à deux facteurs.

## 5. Interactions

- L'utilisateur se présente en conversation (« Je m'appelle Marc, né le 12 mars 1988, j'habite Lyon, j'aime le vélo ») → l'agent enregistre le profil, calcule le signe, confirme en une phrase.
- L'utilisateur demande « qu'est-ce que tu sais de moi ? » → l'agent liste prénom, signe, ville, centres d'intérêt et notes, avec ses mots.
- L'utilisateur dit « retire ma note sur le dentiste » → l'agent cite la note qu'il a trouvée et demande confirmation, puis ne retire que celle-là, et confirme. Si plusieurs notes correspondent, ou aucune, il pose la question au lieu de choisir.
- L'utilisateur dit « oublie-moi » → l'agent demande confirmation, puis efface profil, notes, pense-bêtes reçus et conversations, et confirme.
- Il est 7 h → le brief du jour est généré et enregistré ; s'il existe déjà, rien n'est refait et le journal le mentionne.
- L'utilisateur clique « Générer le brief maintenant » → même génération, immédiate, avec l'anti-doublon contournable pour les tests. Il voit les étapes défiler en direct (outils, réflexion, texte), puis le relevé.
- Un service externe envoie un pense-bête sur le webhook avec le bon jeton → réponse immédiate « reçu », enregistrement, intégration au brief suivant. Sans jeton ou avec un mauvais jeton → refus.
- L'utilisateur ouvre la page web → mot de passe demandé ; puis onglets Chat, Brief du jour, Mémoire, Activité.
- L'utilisateur clique « Se déconnecter » → la page de connexion réapparaît ; la page n'est plus accessible sans mot de passe.
- L'utilisateur coche « Voir les coulisses » → avant chaque réponse, un bloc repliable montre le résumé de raisonnement du modèle, puis chaque appel d'outil avec le JSON de ses arguments et le JSON de son résultat. Si le modèle répond sans outil, le bloc ne montre que la réflexion.
- L'utilisateur demande « explique ce que tu viens de faire » → l'agent raconte son dernier tour, outil par outil, à partir du journal.
- Une source externe ne répond pas (API météo, serveur MCP ou API horoscope, modèle image) → le brief sort quand même, avec un message d'erreur à la place de la section concernée : il dit ce qui a échoué et pourquoi. Aucun contenu de remplacement n'est affiché ni inventé, et le journal note l'échec.

## 6. Spécifications visuelles / d'interface

- **Apparence :** sobre et lisible, page web en quatre onglets (Chat, Brief du jour, Mémoire, Activité). L'image du jour, si présente, s'affiche au-dessus du texte du brief. Les tableaux de la mémoire et du journal sont bruts et complets : c'est une vitrine pédagogique, pas une interface grand public.
- **Comportement :** le chat affiche les réponses mot à mot ; les onglets Mémoire et Activité ont un bouton « Rafraîchir » ; la case « Voir les coulisses » est cochée par défaut, et on peut la décocher pour un affichage épuré ; un interrupteur « détails techniques » dans l'onglet Activité ajoute les durées et les erreurs brutes. Les arguments des outils ne s'y affichent jamais : ils ne se voient qu'en direct, dans les coulisses.

## 7. Contraintes (exigences non-fonctionnelles)

- **Technique :** Python 3.12 ; SDK `google-genai` (API Interactions ; modèles texte et image : ceux que Google recommande à la date du projet, soit le Gemini Flash stable le plus récent pour le texte et le modèle image stable le moins coûteux, recherchés par l'agent dans la documentation officielle et validés par le pilote au moment où la feature en a besoin) ; FastAPI + uvicorn pour le webhook ; Gradio pour la page web ; SQLite pour la base ; bibliothèque `mcp` comme client MCP ; `logging` de la bibliothèque standard ; `httpx` pour les appels HTTP. Code modulaire, un fichier par responsabilité. Aucun secret dans le code : tout en variables d'environnement.
- **Déploiement :** VPS Ubuntu LTS, services `systemd`, Caddy en reverse proxy HTTPS, déploiement automatique par GitHub Actions à chaque push sur `main`. **La mise en ligne se fait sur ce VPS, pas sur Netlify.**
- **Données :** un seul utilisateur, profil fictif recommandé pour la démo. Jamais de donnée personnelle dans les logs, le journal, les tests ni le dépôt Git. Minimisation : le signe suffit, la date de naissance complète n'est pas conservée après calcul. Effacement complet sur demande.
- **Observabilité :** chaque appel au modèle ou à un outil enregistre tokens (entrée, sortie, réflexion), latence et durée, sans donnée personnelle.
- **Coût :** le prompt système, le profil et les outils partent une seule fois par appel au modèle. D'un message au suivant, à nombre de tours égal, les tokens d'entrée n'augmentent que de la taille du dialogue ajouté.
- **Qualité :** au moins un test automatisé par fonctionnalité, exécuté par la CI, sans appel réseau réel. Nombre maximal de tours par exécution de l'agent. Message d'erreur explicite si une source externe échoue, jamais de contenu de remplacement.
- **Erreurs :** une erreur ne se cache jamais : elle se dit et elle s'affiche. Aucune erreur n'est masquée : ni contenu de remplacement, ni valeur par défaut à la place d'une donnée manquante, ni erreur interceptée en silence, ni phrase rassurante. Quand quelque chose échoue (une source, un outil, un fichier, un réglage absent), GoodVibe le dit là où l'utilisateur regarde (le chat, le brief, l'onglet Activité), par un message qui nomme ce qui a échoué et pourquoi ; le journal note l'échec et sa cause ; le reste continue quand c'est possible. L'objectif est pédagogique et pratique : on apprend en voyant ce qui casse, et une panne visible se répare.
- **Performance :** premier mot affiché en moins de 3 secondes en conversation dans les conditions normales de l'API ; brief généré en moins de 60 secondes.
- **Compatibilité :** page web utilisable sur un navigateur de bureau récent ; lisible sur mobile sans être optimisée.
- **Accessibilité :** contrastes suffisants, aucune information portée par la couleur seule.

## 8. Critères de succès

- Le pilote peut, depuis la page web, lire un brief du jour qui s'ouvre sur sa date et son heure et contient horoscope personnalisé et météo, et voir dans l'onglet Activité les appels et les tokens qui l'ont produit.
- Un second lancement du cron le même jour ne produit pas de second brief, et le journal le dit.
- Un pense-bête envoyé par webhook avec le bon jeton apparaît dans le brief suivant ; sans jeton, la requête est refusée.
- Après « retire ma note sur… » et sa confirmation, cette note a disparu de l'onglet Mémoire et des réponses de l'agent ; le profil et les autres notes sont intacts.
- Après « oublie-moi », l'onglet Mémoire est vide et l'agent ne sait plus rien de l'utilisateur.
- Un push sur `main` déclenche le pipeline, la coche verte apparaît, et la page publique reflète le changement sans intervention manuelle sur le VPS.
- Aucune donnée personnelle n'apparaît dans les logs ni dans le dépôt.

## 9. Hypothèses & Questions ouvertes

- **Hypothèses retenues :** la source d'horoscope est une API publique gratuite en anglais (freehoroscopeapi.com), lue via le serveur MCP officiel `fetch` ; si elle ne répond pas, le brief l'indique par un message d'erreur, sans horoscope de remplacement ; la météo vient de l'API Open-Meteo (sans clé), appelée directement, sans MCP ; l'utilisateur unique est identifié par la session, sans compte.
- **À trancher plus tard :** aucune pour la version 1. La version 2 (sous-agents) sera cadrée dans un second cycle à partir de la section « Pour aller plus loin » du plan d'action.
