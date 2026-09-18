# 🤝 Guide de contribution — Job Agent AI

Merci de vouloir contribuer à **Job Agent AI** !

Ce document couvre deux aspects complémentaires :
- **Comment collaborer** sur le projet : organisation du travail, branches, commits, Pull Requests, revue de code.
- **Comment contribuer techniquement** : où placer le code selon l'architecture du projet (superviseur LangGraph, sous-graphe de traitement, Chat Router), comment ajouter un outil ou un connecteur, comment tester avant de proposer une PR.

Avant de contribuer, il est recommandé d'avoir déjà suivi [`GETTING_STARTED.md`](./GETTING_STARTED.md) (installation) et [`API_KEYS.md`](./API_KEYS.md) (clés API), pour pouvoir tester tes changements en conditions réelles.

---

## 📋 Sommaire

* [Avant de commencer](#-avant-de-commencer)
* [Organisation du travail](#-organisation-du-travail)
* [Branches](#-branches)
* [Commits](#-commits)
* [Mettre en place son environnement de travail](#-mettre-en-place-son-environnement-de-travail)
* [Où placer son code](#-où-placer-son-code)
* [Ajouter un nouvel outil](#-ajouter-un-nouvel-outil)
* [Ajouter un nouveau connecteur](#-ajouter-un-nouveau-connecteur)
* [Style de code et bonnes pratiques techniques](#-style-de-code-et-bonnes-pratiques-techniques)
* [Tester sa contribution avant de proposer une PR](#-tester-sa-contribution-avant-de-proposer-une-pr)
* [Pull Requests](#-pull-requests)
* [Garder les Pull Requests faciles à relire](#-garder-les-pull-requests-faciles-à-relire)
* [Revue de code](#-revue-de-code)
* [Discussions et communication](#-discussions-et-communication)
* [Mettre sa branche à jour](#-mettre-sa-branche-à-jour)
* [Résolution des conflits](#️-résolution-des-conflits)
* [Bonnes pratiques de collaboration](#-bonnes-pratiques-de-collaboration)
* [Checklist avant contribution](#-checklist-avant-de-proposer-une-contribution)
* [Idées de contributions bienvenues](#️-idées-de-contributions-bienvenues)
* [Esprit de collaboration](#-esprit-de-collaboration)

---

## 👋 Avant de commencer

Avant de commencer une contribution :

1. Vérifier qu'une issue ou une discussion n'existe pas déjà pour le sujet.
2. Si ce n'est pas le cas, créer une issue expliquant :
   - le problème ou le besoin ;
   - la solution envisagée ;
   - l'impact potentiel sur le superviseur autonome, le Chat Router, ou les deux.
3. Vérifier qu'aucune Pull Request ne traite déjà le même sujet.
4. Pour une modification importante, discuter de l'approche avant de commencer le développement.

L'objectif est d'éviter que plusieurs personnes travaillent indépendamment sur la même modification.

Pour une correction de bug ou un ajustement mineur, tu peux directement proposer un correctif (Pull Request) sans forcément passer par une issue préalable.

---

## 👥 Organisation du travail

Chaque contribution doit avoir un objectif clairement identifiable.

Une contribution peut par exemple concerner :

* une nouvelle fonctionnalité ;
* une correction de bug ;
* une amélioration ;
* une refactorisation ;
* la documentation ;
* les tests ;
* la correction d'un problème de sécurité.

Une contribution importante doit être découpée en plusieurs tâches lorsque cela facilite la revue.

### Issues

Une issue doit expliquer clairement :

**Pour un bug :**

```text
Description :
Comportement attendu :
Comportement observé :
Étapes pour reproduire :
Contexte :
```

**Pour une fonctionnalité :**

```text
Problème :
Objectif :
Comportement attendu :
Proposition :
```

Une issue n'a pas besoin de décrire immédiatement toute la solution technique.

---

## 🌿 Branches

La branche principale doit rester stable.

Il est recommandé de créer une branche dédiée pour chaque contribution.

### Convention de nommage

Utiliser un préfixe indiquant la nature du changement :

```text
feat/<description>
fix/<description>
refactor/<description>
docs/<description>
test/<description>
chore/<description>
```

Exemples :

```text
feat/telegram-notifications
fix/email-parser
refactor/job-processing
docs/update-readme
test/job-analyzer
```

Éviter les noms génériques :

```text
test
update
new
changes
branch1
```

### Une branche = une contribution

Éviter de mélanger plusieurs sujets indépendants dans une même branche.

Par exemple, une branche ne devrait pas simultanément :

* corriger un bug Gmail ;
* modifier le dashboard ;
* ajouter une fonctionnalité Telegram ;
* refactoriser une partie du projet.

Ces changements doivent idéalement être séparés.

---

## 💾 Commits

Les commits doivent être compréhensibles et représenter des changements cohérents.

### Format recommandé

Utiliser un préfixe :

```text
feat:
fix:
refactor:
docs:
test:
chore:
```

Exemples :

```text
feat: add application approval notification
fix: handle missing recruiter email
refactor: simplify job processing
docs: update contribution guide
test: add parser regression tests
chore: update project dependencies
```

### Éviter les commits vagues

À éviter :

```text
update
fix
changes
work
final
final2
test
```

Un message de commit doit permettre de comprendre rapidement ce qui a changé.

### Commits cohérents

Privilégier plusieurs commits logiques plutôt qu'un énorme commit contenant toutes les modifications.

Exemple :

```text
feat: add recruiter notification
test: cover recruiter notification
docs: document recruiter notification
```

plutôt que :

```text
update everything
```

---

## 🌱 Mettre en place son environnement de travail

```bash
git clone <URL_DU_REPOSITORY>
cd job-agent-ai
git checkout -b feat/ma-contribution
```

Configure ton `.env` local (voir [`API_KEYS.md`](./API_KEYS.md)), puis lance le projet en mode développement :

```bash
docker compose up -d --build
```

Le code source est monté en volume (`.:/app`) : les modifications Python sont prises en compte après un simple redémarrage du service concerné :

```bash
docker compose restart agent dashboard
```

Toute modification de `requirements.txt` ou du `Dockerfile` nécessite un rebuild complet :

```bash
docker compose build --no-cache
docker compose up -d
```

---

## 🗂️ Où placer son code

Respecte la séparation déjà en place dans le projet :

| Type de changement | Emplacement |
|---|---|
| Logique métier pure (sans LangChain) | `src/tools/` |
| Outil `@tool` pilotable par le superviseur autonome | `src/agent/tools.py` |
| Outil `@tool` spécifique au chat conversationnel | `src/agent/Chat_Router/tools_web.py` |
| Client d'API externe (auth + appels réseau) | `src/connectors/` |
| Nœud ou routage du graphe superviseur / sous-graphe | `src/agent/nodes.py`, `src/agent/graph.py` |
| Nœud ou routage du graphe du Chat Router | `src/agent/Chat_Router/chat_router_graph.py` |
| État partagé d'un graphe | `src/agent/state.py`, `src/agent/Chat_Router/chat_state.py` |
| Interface Streamlit | `src/dashboard/` |

Un outil doit toujours rester un **wrapper mince** : la logique lourde vit dans `src/tools/` ou `src/connectors/`, jamais directement dans la docstring `@tool`.

---

## 🧰 Ajouter un nouvel outil

1. Implémente la logique métier dans `src/tools/`, sans dépendance à LangChain.
2. Expose-la via `@tool` dans `src/agent/tools.py` ou `tools_web.py`, avec une **docstring claire et précise** (c'est ce texte que le LLM lit pour décider quand appeler l'outil).
3. Ajoute l'outil à `ALL_AGENT_TOOLS` et/ou `ALL_CHAT_TOOLS` selon son usage.
4. **Si l'outil a un effet irréversible** (envoi de message, paiement, suppression, action sur un tiers), ajoute-le à `SENSITIVE_TOOLS` dans `chat_router_graph.py`, pour qu'il passe par le nœud `confirm` (donc par un `interrupt()`) avant toute exécution en conversation libre.
5. Mets à jour les prompts système concernés (`nodes.py::decide_autonomy_node` et/ou `chat_router_graph.py::agent_node`) pour que le LLM sache quand et comment l'utiliser.
6. Documente le nouvel outil dans le README (section *Ajouter un outil ou un connecteur*) si son usage n'est pas évident.

Voir la section correspondante du [`README.md`](./README.md#-ajouter-un-outil-ou-un-connecteur) pour le détail complet.

---

## 🔌 Ajouter un nouveau connecteur

1. Crée un client dédié dans `src/connectors/`, qui encapsule l'authentification et les appels réseau — sur le modèle de `gmail_client.py`, `telegram_bot.py` ou `france_travail.py`. Ce client ne doit rien savoir du LLM ni du tool calling.
2. Ajoute les identifiants nécessaires dans `.env.example` (pas seulement ton `.env` local) et dans `src/config.py` (`Settings`), pour que les autres contributeurs sachent quelles variables renseigner.
3. Documente comment obtenir ces identifiants dans [`API_KEYS.md`](./API_KEYS.md), en suivant le même format que les sections existantes (lien direct, étapes numérotées, variable d'environnement correspondante).
4. Si le connecteur doit être pilotable par le LLM, expose une ou plusieurs méthodes via `@tool` (voir ci-dessus).
5. Si c'est un nouveau canal d'entrée conversationnel, instancie un `ChatRouter` avec un `chat_id` propre au canal, sur le modèle de `start_telegram_listener()` dans `src/main.py`.
6. Ajoute le service au `docker-compose.yml` si un processus séparé est nécessaire.

---

## ✅ Style de code et bonnes pratiques techniques

- **Python** : suis le style déjà en place (type hints, `structlog` pour les logs, gestion d'erreurs explicite avec messages clairs — voir `france_travail.py` ou `mcp_playwright_tool.py` comme exemples).
- **Logs** : utilise des préfixes d'emoji cohérents avec l'existant (`🔑`, `❌`, `✅`, `⚡`, `♻️`, etc.) pour rester lisible dans `docker compose logs`.
- **Docstrings des outils `@tool`** : écris-les à l'attention du LLM, pas seulement des développeurs — sois précis sur les paramètres attendus et ce que l'outil retourne.
- **Pas de secrets en dur** : toute clé, token ou identifiant passe par `.env` et `src/config.py`, jamais codé en dur dans le code (voir la section *Sécurité* de `GETTING_STARTED.md`).
- **Statuts d'offre** : si ta contribution touche au cycle de vie d'une offre, respecte strictement `VALID_JOB_STATUSES` (défini dans `src/agent/tools.py`) — n'introduis jamais un nouveau statut sans l'ajouter à cet ensemble et au tableau du README.

---

## 🧪 Tester sa contribution avant de proposer une PR

Avant d'ouvrir une Pull Request, vérifie au minimum :

* [ ] le service `agent` démarre sans erreur (`docker compose logs -f agent`) ;
* [ ] si tu as touché au superviseur : un cycle complet (`inspect → fetch → process → sleep`) s'exécute sans exception, et les offres Zone Rouge/Orange/Verte suivent bien le routage attendu (voir section 11 de `GETTING_STARTED.md`) ;
* [ ] si tu as touché au Chat Router : une action sensible déclenche toujours une confirmation (`interrupt()`), et la reprise après `oui`/`non` fonctionne, y compris après un redémarrage du service (voir section 18) ;
* [ ] si tu as ajouté une dépendance : elle est bien listée dans `requirements.txt`, et un rebuild complet (`docker compose build --no-cache`) fonctionne sans erreur ;
* [ ] si tu as ajouté une clé API : elle est documentée dans [`API_KEYS.md`](./API_KEYS.md) et ajoutée à l'exemple `.env` dans [`GETTING_STARTED.md`](./GETTING_STARTED.md) ;
* [ ] LangSmith (si activé chez toi) ne montre pas d'appel LLM anormal ou de tool call simulé introduit par ta modification (voir section 12 de `GETTING_STARTED.md`).

---

## 🔀 Pull Requests

Toute modification destinée à être intégrée à la branche principale doit passer par une Pull Request.

Une Pull Request doit permettre à une autre personne de comprendre rapidement :

* pourquoi la modification existe ;
* ce qui a été changé ;
* comment elle a été vérifiée ;
* s'il existe des points nécessitant une attention particulière.

### Titre

Le titre doit être court et explicite.

Exemples :

```text
feat: add Telegram application notifications
fix: prevent duplicate applications
docs: improve contribution guide
```

### Description

Utiliser une structure similaire à :

```markdown
## Pourquoi ?

Décrire le problème ou le besoin.

## Qu'est-ce qui change ?

Décrire les modifications principales.

## Comment vérifier ?

Décrire les vérifications effectuées (voir la checklist de tests ci-dessus).

## Points d'attention

Mentionner les éventuels risques ou choix importants.
```

---

## 🧩 Garder les Pull Requests faciles à relire

Une Pull Request doit rester aussi ciblée que possible.

Éviter d'y inclure des changements sans rapport avec le sujet :

* reformatage massif ;
* renommage de fichiers sans rapport ;
* refactorisation opportuniste ;
* modifications de documentation non liées ;
* changements de style sur des fichiers qui ne sont pas concernés.

Si une amélioration est découverte pendant le développement mais n'est pas nécessaire à la contribution actuelle, créer une issue séparée.

---

## 👀 Revue de code

La revue de code est une collaboration, pas uniquement une validation.

Les commentaires doivent porter principalement sur :

* la correction ;
* la compréhension du code ;
* la maintenabilité ;
* les effets de bord ;
* les tests ;
* la cohérence avec le projet.

### Pour l'auteur

Lorsqu'une remarque est faite :

* répondre lorsque cela nécessite une explication ;
* effectuer les modifications demandées lorsque cela est pertinent ;
* expliquer clairement lorsqu'un autre choix technique est préférable ;
* éviter les échanges personnels.

### Pour le reviewer

Privilégier les remarques concrètes.

❌ À éviter :

```text
Ce code est mauvais.
```

✅ Préférer :

```text
Cette partie pourrait provoquer un traitement en double lorsque
deux exécutions arrivent simultanément. Peux-tu vérifier ce cas ?
```

Les désaccords techniques doivent être résolus par la discussion et, lorsque possible, par des éléments vérifiables : tests, comportement attendu, documentation ou contraintes du projet.

---

## 💬 Discussions et communication

Utiliser le bon espace pour chaque sujet.

### Issue

Pour :

* bugs ;
* fonctionnalités ;
* problèmes identifiés ;
* tâches à réaliser.

### Pull Request

Pour :

* discuter d'une modification précise ;
* commenter le code ;
* demander des changements ;
* valider une implémentation.

### Discussions

Pour :

* questions générales ;
* propositions importantes ;
* décisions d'architecture ;
* sujets qui nécessitent une discussion avant développement.

Éviter de transformer une Pull Request en discussion générale sur plusieurs sujets indépendants.

---

## 🔄 Mettre sa branche à jour

Avant de demander une revue, vérifier que la branche est à jour avec la branche principale.

Selon le workflow utilisé par le projet :

```bash
git fetch origin
git rebase origin/main
```

ou utiliser la méthode de synchronisation définie par les mainteneurs.

En cas de doute, demander avant de réécrire l'historique d'une branche partagée.

### Ne pas forcer sur une branche partagée

Éviter :

```bash
git push --force
```

sur une branche utilisée par plusieurs personnes.

Si un `force push` est réellement nécessaire sur sa propre branche de Pull Request, utiliser de préférence :

```bash
git push --force-with-lease
```

---

## ⚔️ Résolution des conflits

En cas de conflit :

1. récupérer les dernières modifications ;
2. identifier les changements des deux côtés ;
3. résoudre le conflit sans supprimer involontairement le travail d'un autre contributeur ;
4. vérifier la modification résultante ;
5. effectuer les vérifications nécessaires (voir la checklist de tests) ;
6. poursuivre la Pull Request.

Ne pas résoudre un conflit uniquement en choisissant systématiquement :

```text
ours
```

ou :

```text
theirs
```

sans comprendre les modifications concernées.

---

## 🧹 Bonnes pratiques de collaboration

### Ne pas modifier le travail des autres sans raison

Éviter de réécrire ou supprimer le travail d'un autre contributeur sans en discuter lorsque cela affecte sa contribution.

### Documenter les décisions importantes

Lorsqu'une décision influence durablement le projet, la documenter dans l'issue, la Pull Request ou la documentation appropriée (README, GETTING_STARTED, API_KEYS).

### Préférer les petites contributions

Une petite Pull Request ciblée est généralement plus facile à comprendre, discuter et maintenir qu'une modification massive.

### Respecter les contributions existantes

Avant de modifier une partie du projet, vérifier son contexte et les raisons des choix existants.

### Donner du contexte

Lorsqu'une décision n'est pas évidente, expliquer **pourquoi** elle a été prise et pas uniquement **ce qui a été changé**.

### Garder la documentation cohérente

Si ta contribution touche à la documentation (README, GETTING_STARTED, API_KEYS), garde le même format et la même structure que les fichiers existants pour que l'ensemble reste cohérent.

---

## 🚦 Checklist avant de proposer une contribution

Avant d'ouvrir une Pull Request :

* [ ] Une issue existe ou le besoin a été clairement identifié.
* [ ] La branche concerne un seul sujet principal.
* [ ] Le nom de la branche est explicite.
* [ ] Les commits sont compréhensibles.
* [ ] Les changements sans rapport ont été retirés.
* [ ] La description de la Pull Request explique le changement.
* [ ] Les vérifications techniques nécessaires ont été effectuées (voir la checklist de tests).
* [ ] Les éventuels points d'attention sont indiqués.
* [ ] La branche est à jour avec la branche principale.
* [ ] Aucun travail d'un autre contributeur n'a été écrasé involontairement.

---

## 🗺️ Idées de contributions bienvenues

La section [Pistes d'évolution](./README.md#️-pistes-dévolution) du README liste des axes déjà identifiés, notamment :

- rôle PostgreSQL en lecture seule pour sécuriser `action_query_database` ;
- migration du checkpointer du Chat Router vers un backend multi-instances (`PostgresSaver`) ;
- préchargement automatique du modèle Ollama au démarrage ;
- ajout d'une colonne `updated_at` sur `JobModel` ;
- tags/metadata LangSmith par offre et par thread de conversation ;
- mise en cache des résultats de `action_read_web_pages`.

Toute autre proposition cohérente avec l'architecture (graphe superviseur déterministe + LLM, Chat Router avec confirmation HITL) est la bienvenue — ouvre une issue pour en discuter avant de te lancer sur un gros morceau.

---

## 🤝 Esprit de collaboration

Le projet repose sur une collaboration ouverte et constructive.

Les désaccords techniques sont normaux. Ils doivent être traités autour :

* du problème à résoudre ;
* des contraintes du projet ;
* des éléments techniques vérifiables ;
* de la maintenabilité ;
* de l'expérience des utilisateurs.

L'objectif d'une revue n'est pas de défendre une implémentation particulière, mais d'améliorer collectivement le projet.

Merci à toutes les personnes qui contribuent à **Job Agent AI** ❤️