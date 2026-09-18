# 🤖 Job Agent AI

**Agent autonome de recherche d'alternance piloté par LLM.** Il analyse des offres d'emploi, évalue leur adéquation avec un profil candidat via un score ATS, et postule automatiquement — via un navigateur (Playwright MCP) ou par e-mail — avec validation humaine intégrée pour les cas ambigus ou sensibles.

Contrairement à un pipeline procédural classique (`if score >= seuil: postule`), la décision est **pilotée par un LLM via tool calling** : le modèle choisit lui-même les outils à appeler (génération de CV, candidature, rejet) et explicite son raisonnement à chaque étape, sous la contrainte de garde-fous déterministes côté code.

> 👋 Nouveau sur le projet ? Suis les guides dans cet ordre :
> 1. [`GETTING_STARTED.md`](./GETTING_STARTED.md) — installation et premier lancement, pas à pas.
> 2. [`API_KEYS.md`](./API_KEYS.md) — comment obtenir chaque clé API/token nécessaire, avec les liens directs.
> 3. [`CONTRIBUTING.md`](./CONTRIBUTING.md) — comment proposer une amélioration ou un correctif.

---

## Sommaire

- [Fonctionnalités](#-fonctionnalités)
- [Architecture](#️-architecture)
- [Services Docker Compose](#-services-docker-compose)
- [Statuts d'une offre](#statuts-dune-offre)
- [Configuration](#️-configuration)
- [Observabilité (LangSmith)](#-observabilité-langsmith)
- [Lancement](#️-lancement)
- [Logique de décision](#-logique-de-décision)
- [Le Chat Router : graphe conversationnel avec confirmation HITL](#-le-chat-router--graphe-conversationnel-avec-confirmation-hitl)
- [Ajouter un outil ou un connecteur](#-ajouter-un-outil-ou-un-connecteur)
- [Résilience & sécurité](#️-résilience--sécurité)
- [Stack technique](#-stack-technique)
- [Limitations connues](#-limitations-connues)
- [Pistes d'évolution](#️-pistes-dévolution)

---

## ✨ Fonctionnalités

- **Récupération automatique des offres d'emploi** via l'**API officielle France Travail** (authentification OAuth2 client_credentials, avec cache et renouvellement automatique du jeton), selon un profil de recherche configurable.
- **Analyse ATS** : score de correspondance CV/offre (compétences techniques, expérience, deal-breakers) généré par LLM.
- **Décision autonome par zones d'autonomie** (Verte / Orange / Rouge) : le LLM appelle lui-même `action_generate_cv`, `action_apply_via_browser`, `action_send_email` ou `action_reject_offer` selon des seuils indicatifs de score ATS.
- **Filtrage amont déterministe** : les offres en Zone Rouge sont écartées avant même l'appel au LLM de décision (aiguillage `check_if_rejected`), ce qui évite un appel modèle inutile sur des offres déjà disqualifiées par le score ATS.
- **Génération de CV sur-mesure** au format Pdf/Word, avec préservation du formatage d'origine.
- **Candidature automatisée** :
  - via navigateur, piloté par le **serveur MCP Playwright de Microsoft** (`@playwright/mcp`), pour les offres en Zone Verte selon la config,
  - via e-mail (Gmail API), avec rédaction du message par le LLM sinon.
- **Validation humaine (HITL)**, sur deux canaux complémentaires, chacun avec son propre mécanisme technique :
  - via boutons interactifs Telegram (Approuver/Rejeter) pour les offres en Zone Orange du superviseur autonome (état en base de données) ;
  - via un **graphe LangGraph dédié** (`chat_router_graph.py`) pour le chat conversationnel, qui **interrompt réellement l'exécution** (`interrupt()`) avant toute action sensible et persiste cet état en attente sur disque (SQLite) optionnel — voir [Le Chat Router](#-le-chat-router--graphe-conversationnel-avec-confirmation-hitl).
- **Chat conversationnel** (Telegram + dashboard web) pour interroger l'état des candidatures, lire et résumer des offres à partir d'une URL, effectuer des recherches web, et déclencher des actions en langage naturel.
- **Recherche et lecture web pour le chat** : le routeur conversationnel peut chercher sur le web (DuckDuckGo) et lire le contenu réel d'une page (extraction légère `httpx` + `trafilatura`, avec repli automatique sur un navigateur headless `crawl4ai` pour les sites dynamiques).
- **Dashboard web** (Streamlit) pour visualiser l'activité de l'agent sans dépendre uniquement de Telegram.
- **Résilience multi-fournisseurs LLM** : bascule automatique Groq → Gemini → Ollama local en cas de quota épuisé, avec tool calling propagé à chaque niveau de secours.
- **Auto-réparation de la file d'attente** : au démarrage de chaque cycle d'inspection, les offres restées bloquées en `PROCESSING` au-delà de 15 minutes (crash, redémarrage) sont automatiquement remises en `NEW`.
- **Observabilité complète via LangSmith** : traçage de chaque exécution du graphe superviseur, du sous-graphe de traitement et du graphe du Chat Router (appels LLM, tool calls, interrupts, latences, tokens), pour déboguer et auditer le raisonnement de l'agent de bout en bout.
- **Statuts de candidature cohérents et traçables**, avec audit trail complet en base de données.

---

## 🏗️ Architecture

```
job-agent-ai/
├── src/
│   ├── agent/
│   │   ├── tools.py                    # Outils @tool pilotables par le LLM (wrappers minces)
│   │   ├── nodes.py                    # Nœuds du sous-graphe de traitement (analyse, décision, sauvegarde)
│   │   ├── state.py                    # État partagé du graphe superviseur (MasterAgentState / AgentState)
│   │   ├── graph.py                    # Graphe superviseur + sous-graphe de traitement (LangGraph)
│   │   └── Chat_Router/
│   │       ├── chat_router_graph.py    # Graphe LangGraph du chat conversationnel (agent/confirm/tools)
│   │       ├── chat_state.py           # État du graphe du Chat Router (ChatRouterState)
│   │       ├── tools_web.py            # Outils web du chat (recherche DuckDuckGo, lecture de pages)
│   │       └── checkpoints.db          # Checkpointer SQLite (persistance des interrupts, non versionné)
│   ├── tools/
│   │   ├── ats_analyzer.py         # Analyse ATS (score, compétences manquantes, justification)
│   │   ├── cv_generator.py         # Génération de CV Word sur-mesure
│   │   ├── mcp_playwright_tool.py  # Automatisation via le serveur MCP Playwright (Microsoft)
│   │   ├── db_query.py             # Requêtage BDD (filtres structurés ou SQL brut encadré)
│   │   └── utils/
│   ├── connectors/
│   │   ├── gmail_client.py       # Envoi d'e-mails de candidature via Gmail API
│   │   ├── telegram_bot.py       # Notifications et interactions HITL via Telegram
│   │   ├── france_travail.py     # Authentification OAuth2 et requêtes vers l'API France Travail
│   │   └── email_parser.py       # Classification des réponses de recruteurs
│   ├── dashboard/
│   │   ├── app.py            # Dashboard web Streamlit
│   │   └── chat_router.py    # Adaptateur ChatRouter : expose route_intent() au-dessus du graphe LangGraph
│   ├── scraper/
│   │   └── job_fetcher.py    # Récupération des offres via l'API France Travail
│   ├── config.py             # Chargement de la configuration (YAML + variables d'env)
│   ├── database.py           # Modèles SQLAlchemy (JobModel, ApplicationModel)
│   ├── llm_client.py         # Client LLM unifié avec fallback en cascade
│   └── main.py                # Point d'entrée du service "agent" (superviseur + bot Telegram)
├── assets/
│   └── master_cv.docx        # CV maître (template avec placeholders)
├── outputs/                  # CV générés à la volée
├── config.yaml                # Configuration du candidat et du profil de recherche
├── credentials.json            # Identifiants OAuth Google (non versionné)
├── docker-compose.yml         # Orchestration des services (db, ollama, agent, dashboard)
├── Dockerfile
└── README.md
```

### Le graphe superviseur : boucle infinie à quatre phases

`graph.py` définit un **méta-graphe superviseur** (`create_job_agent_graph`) qui tourne en continu tant que le service `agent` vit, et gère lui-même les transitions entre quatre phases via `state["phase"]` :

```
┌──────────┐     ┌───────┐     ┌─────────┐     ┌───────┐
│ inspect  │ ──▶ │ fetch │ ──▶ │ process │ ──▶ │ sleep │
└────┬─────┘     └───┬───┘     └────┬────┘     └───┬───┘
     │               │              │              │
     └───────────────┴──────────────┴──────────────┘
                (retour vers inspect selon la phase)
```

- **`inspect`** : audite la base — recompte les offres `NEW`, et remet en file toute offre restée bloquée en `PROCESSING` depuis plus de 15 minutes (garde-fou anti-crash). Décide ensuite si on part traiter (`process`) ou récupérer de nouvelles offres (`fetch`).
- **`fetch`** : interroge l'API France Travail si le stock est vide, insère les nouvelles offres en base (dédupliquées par URL/identifiant d'offre) avec le statut `NEW`, et notifie Telegram du nombre d'offres détectées.
- **`process`** : dépile **toutes** les offres `NEW` en séquence dans la même session DB. Pour chaque offre, il invoque le **sous-graphe de traitement** (voir ci-dessous), applique le statut retourné (validé contre `VALID_JOB_STATUSES`), notifie Telegram, et gère les erreurs 429 avec un backoff exponentiel (compteur `consecutive_429`).
- **`sleep`** : pause adaptative — backoff exponentiel (jusqu'à 15 min) en cas de rate limit, sinon veille standard d'1 heure avant de relancer `inspect`.

### Le sous-graphe de traitement d'une offre

Chaque offre `NEW` dépilée par `process` est traitée par un **sous-graphe compilé indépendamment** (`processing_app`, construit par `create_processing_subgraph`) :

```
              ┌──────────────┐
              │ analyze_job  │  (score ATS, filtrage amont)
              └──────┬───────┘
                     │
           check_if_rejected (aiguillage déterministe)
                     │
        ┌────────────┴────────────┐
        │ REJECTED                │ QUALIFIED
        ▼                         ▼
   ┌─────────┐            ┌─────────────────┐
   │ save_job│            │ decide_autonomy │  (LLM + tool calling)
   └─────────┘            └────────┬────────┘
                                    │
                          tools_condition (LangGraph)
                                    │
                     ┌──────────────┴──────────────┐
                     │ tool_calls présents          │ pas de tool_calls
                     ▼                              ▼
                ┌─────────┐                   ┌─────────┐
                │  tools  │ ─────────────────▶│ save_job│
                │(ToolNode)│                   └─────────┘
                └─────────┘
```

Points clés de cette architecture :
- **`check_if_rejected`** court-circuite l'appel LLM pour les offres déjà rejetées en Zone Rouge par `analyze_job` (score sous le seuil) : pas de tool calling inutile, l'offre va directement en sauvegarde avec le statut `REJECTED`.
- **`tools_condition`** (utilitaire natif LangGraph) route automatiquement vers le nœud `tools` (un `ToolNode` standard exécutant `ALL_AGENT_TOOLS`) si le LLM a émis des tool calls dans `decide_autonomy`, ou directement vers `save_job` sinon (typiquement le cas de la Zone Orange, où aucun outil de candidature n'est appelé).
- Le sous-graphe est **compilé une seule fois** au chargement du module (`processing_app = create_processing_subgraph()`) et invoqué autant de fois que nécessaire, une invocation par offre, avec un état frais à chaque fois.

---

## 🐳 Services Docker Compose

Le projet se lance intégralement via `docker-compose.yml`, avec quatre services :

| Service | Rôle | Port exposé |
|---|---|---|
| `db` | PostgreSQL 15 — stockage des offres, candidatures et audit trail | `5432` |
| `ollama` | LLM local (`llama3.2`), dernier niveau de la cascade de secours (Groq → Gemini → Ollama) | `11434` |
| `agent` | Service principal : superviseur autonome + écouteur Telegram (`src/main.py`) | — |
| `dashboard` | Interface web Streamlit (`src/dashboard/app.py`) | `8501` |

`agent` et `dashboard` partagent la même image (buildée depuis le `Dockerfile` à la racine) mais exécutent des commandes différentes. Les deux dépendent de `db` et `ollama`, et montent le code du projet en volume (`.:/app`) pour un rechargement facile en développement. Les variables `LANGCHAIN_*` (voir [Observabilité](#-observabilité-langsmith)) doivent être propagées à ces deux services pour que le traçage fonctionne côté superviseur comme côté chat.

Le service `agent` a également besoin d'un environnement Node.js pour lancer le serveur MCP Playwright (`npx -y @playwright/mcp`), utilisé par `action_apply_via_browser` — voir la note dans le `Dockerfile` et la section [Ajouter un outil ou un connecteur](#-ajouter-un-outil-ou-un-connecteur).

> Le fichier `src/agent/Chat_Router/checkpoints.db` (SQLite) est créé et écrit par le service qui exécute le Chat Router en production (typiquement `agent`, via le bot Telegram). S'il est amené à tourner sur plusieurs instances ou services distincts, ce fichier doit être sur un volume partagé pour que les conversations en attente de confirmation survivent aux redémarrages/redistributions de charge.

### Statuts d'une offre

| Statut | Signification |
|---|---|
| `NEW` | Offre récupérée, pas encore analysée |
| `PROCESSING` | En cours de traitement (verrou anti-doublon) |
| `ANALYZED` | Score ATS calculé |
| `CV_READY` | CV sur-mesure généré |
| `PENDING_APPROVAL` | En attente de validation humaine (Telegram) |
| `APPLIED` | Candidature envoyée avec succès |
| `BROWSER_FAILED` | Échec de la candidature via navigateur |
| `EMAIL_FAILED` | Échec de l'envoi de l'e-mail |
| `REJECTED` | Offre écartée (score insuffisant ou deal-breaker) |

---

## ⚙️ Configuration

### `.env` (à la racine, non versionné)

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/job_agent_db
GROQ_API_KEY=ta_cle_groq
GOOGLE_API_KEY=ta_cle_gemini
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2

# France Travail (remplace l'ancien scraping Apify)
FRANCETRAVAIL_CLIENT_ID=ton_client_id
FRANCETRAVAIL_CLIENT_SECRET=ton_client_secret

TELEGRAM_BOT_TOKEN=ton_token_bot
TELEGRAM_CHAT_ID=ton_chat_id
GMAIL_TOKEN_PATH=token.json
FORCED_LLM_PROVIDER=

# Chat Router : chemin du checkpointer SQLite (optionnel, valeur par défaut suffisante en général)
CHAT_ROUTER_DB_PATH=/app/src/agent/Chat_Router/checkpoints.db

# Observabilité LangSmith (optionnel mais recommandé)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ta_cle_langsmith
LANGCHAIN_PROJECT=job-agent-ai
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

> Note : `DATABASE_URL` et `OLLAMA_BASE_URL` utilisent les noms de service Docker (`db`, `ollama`), pas `localhost` — c'est déjà le cas dans `docker-compose.yml`, qui les surcharge de toute façon via `environment:`. Le `.env` sert surtout aux clés API externes (Groq, Gemini, France Travail, Telegram, Gmail, LangSmith).

> `FORCED_LLM_PROVIDER` est optionnel : laisse vide pour la cascade automatique Groq → Gemini → Ollama, ou force `"gemini"` / `"ollama"` pour un test manuel.

> `CHAT_ROUTER_DB_PATH` pointe par défaut vers un fichier local à côté de `chat_router_graph.py` si la variable n'est pas définie — à surcharger si le conteneur doit écrire ce fichier sur un volume monté.

> **Où obtenir chacune de ces clés ?** Voir le guide dédié [`API_KEYS.md`](./API_KEYS.md), qui détaille pas à pas comment créer les comptes/applications nécessaires (Groq, Google/Gemini, France Travail Connect, Telegram BotFather, Google Cloud/Gmail, LangSmith).

### `config.yaml` (profil candidat et recherche)

```yaml
candidate:
  full_name: "Prénom Nom"
  email: "email@exemple.com"
  phone: "+33 6 00 00 00 00"
  location: "Île-de-France"
  summary_template: "résumé personnalisé ici avec tes propres mots..."
  education:
    degree: "Master of Science en Ingénierie Data"
    school: ""

search_profile:
  active_profile_name: "data_engineering"
  profiles:
    data_engineering:
      contract_types: ["Alternance"]
      target_titles: ["Data Engineer", "Data Analyst"]
      locations: ["Paris", "Île-de-France"]
      rhythm: "3 semaines entreprise / 1 semaine école"
      min_ats_score: 75
      master_cv_path: "./assets/master_cv.docx"
      max_jobs_per_run: 120

autonomy_thresholds:
  zone_verte_auto_apply: 85
  zone_orange_hitl: 75
  zone_rouge_reject: 60
```

Le CV maître (`master_cv.docx`) doit contenir les placeholders `{{TAILORED_SUMMARY}}` et `{{TAILORED_SKILLS}}`, remplacés dynamiquement à chaque candidature en préservant le formatage d'origine.

---

## 🔭 Observabilité (LangSmith)

Le projet s'intègre avec [LangSmith](https://smith.langchain.com) pour tracer l'exécution du graphe superviseur, du sous-graphe de traitement et du graphe du Chat Router : chaque invocation de `analyze_job`, `decide_autonomy` (avec ses tool calls), `tools`, `save_job`, ainsi que `agent` / `confirm` côté chat, remonte comme une trace exploitable, avec les prompts exacts envoyés au LLM, les réponses, les tokens consommés et la latence.

### Activation

1. Créer un compte et un projet sur [smith.langchain.com](https://smith.langchain.com) et récupérer une clé API (détails dans [`API_KEYS.md`](./API_KEYS.md#-langsmith)).
2. Renseigner dans `.env` :
   ```env
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=ta_cle_langsmith
   LANGCHAIN_PROJECT=job-agent-ai
   ```
3. Redémarrer le service `agent` :
   ```bash
   docker compose restart agent
   ```

### Ce que ça permet de vérifier

- Que le LLM effectue bien un **vrai tool call natif** (`response.tool_calls`) et non une simulation en texte libre (voir la section diagnostic de `GETTING_STARTED.md`).
- Le raisonnement complet de `decide_autonomy_node` par offre (Zone Orange vs Verte), utile pour ajuster les prompts sans avoir à relire les logs bruts.
- Les bascules de la cascade LLM (Groq → Gemini → Ollama) et les éventuels échecs de parsing JSON de l'analyse ATS.
- Le chemin exact emprunté par le sous-graphe (`analyze_job → save_job` en cas de rejet amont, ou `analyze_job → decide_autonomy → tools → save_job` en cas de Zone Verte).
- Côté Chat Router, le moment exact où un `interrupt()` est déclenché, le message de confirmation généré, et si la réponse de reprise (`Command(resume=...)`) a été interprétée comme une confirmation ou une annulation.

Si `LANGCHAIN_TRACING_V2` n'est pas défini (ou vaut `false`), l'agent fonctionne normalement sans aucune dépendance à LangSmith — le traçage est strictement additif.

---

## ▶️ Lancement

```bash
docker compose up --build
```

Cette commande :
1. build l'image de l'application depuis le `Dockerfile`,
2. démarre PostgreSQL et Ollama,
3. démarre le service `agent` (superviseur autonome + bot Telegram),
4. démarre le `dashboard` sur [http://localhost:8501](http://localhost:8501).

Pour lancer en arrière-plan :

```bash
docker compose up -d --build
```

Pour arrêter :

```bash
docker compose down
```

Pour tout réinitialiser, y compris les données PostgreSQL et le modèle Ollama téléchargé :

```bash
docker compose down -v
```

Guide détaillé pas à pas, pour un premier lancement : voir [`GETTING_STARTED.md`](./GETTING_STARTED.md).

### Chat conversationnel

```
Toi : où en est ma candidature chez Google ?
Bot : [interroge la BDD avec company="Google" et répond en français]

Toi : trouve-moi des offres Data Engineer alternance à Paris
Bot : [recherche sur le web via DuckDuckGo et résume les résultats]

Toi : https://exemple-offre.com/data-engineer-alternance
Bot : [lit la page réelle, résume le poste et donne un diagnostic d'adéquation avec le profil]

Toi : envoie un mail à l'entreprise Acme pour le poste de Data Engineer
Bot : ⚠️ Confirmation requise — Je m'apprête à envoyer un e-mail de candidature
      à Acme pour le poste Data Engineer, à l'adresse recrutement@...
      Confirmes-tu l'envoi ?

Toi : oui, vas-y
Bot : [reprend le graphe interrompu, exécute l'envoi réel et confirme le résultat]
```

Toute action à effet irréversible demandée en conversation libre (`action_send_email`, `action_apply_via_browser`, `action_reject_offer`) suit ce protocole de confirmation avant exécution réelle, via un mécanisme d'**interruption de graphe persistante** — voir [Le Chat Router](#-le-chat-router--graphe-conversationnel-avec-confirmation-hitl) et [Résilience & sécurité](#️-résilience--sécurité).

---

## 🧠 Logique de décision

Le sous-graphe de traitement enchaîne trois étapes déterministes/LLM pour chaque offre :

1. **`analyze_job`** : calcule le score ATS et applique un **filtrage amont déterministe** — toute offre sous le seuil `zone_rouge_reject` est marquée `REJECTED` immédiatement, sans jamais solliciter le LLM de décision.
2. **`decide_autonomy`** (uniquement pour les offres qualifiées) : le LLM reçoit le profil du candidat, les seuils d'autonomie (à titre indicatif) et les détails de l'offre, puis :
   - **Zone Orange** (score intermédiaire) : n'appelle aucun outil de candidature ; le statut `PENDING_APPROVAL` est attribué de façon déterministe côté code (pas par le LLM) dès lors que le score est sous `zone_verte_auto_apply` ;
   - **Zone Verte** (score élevé) : appelle `action_generate_cv` puis `action_apply_via_browser` (candidature en ligne, pilotée par le serveur MCP Playwright) ou `action_send_email` (sinon) — candidature envoyée automatiquement, sans validation humaine. Le routage `tools_condition` du sous-graphe se charge d'exécuter ces tool calls via le `ToolNode` avant de sauvegarder.
3. **`save_job`** : persiste l'offre, le score, l'audit trail (y compris les pistes d'amélioration de CV) en base, et déclenche la notification Telegram interactive si le statut est `PENDING_APPROVAL`.

Un garde-fou strict (`VALID_JOB_STATUSES`) empêche qu'un statut incohérent ou halluciné soit persisté en base : toute anomalie retombe sur `PENDING_APPROVAL` par sécurité.

Dans le chat conversationnel, la logique diffère volontairement : il n'y a pas de notion de score ni de zone, et **toute** action irréversible passe systématiquement par une confirmation explicite, indépendamment du contexte — voir la section suivante.

---

## 💬 Le Chat Router : graphe conversationnel avec confirmation HITL

Le chat conversationnel (Telegram + dashboard) n'est plus un simple routeur d'intentions procédural : c'est un **graphe LangGraph à part entière** (`src/agent/Chat_Router/chat_router_graph.py`), avec son propre état (`ChatRouterState`) et sa propre persistance.

### Le graphe

```
                ┌───────┐
      ┌────────▶│ agent │
      │         └───┬───┘
      │             │
      │      route_after_agent
      │             │
      │   ┌─────────┼─────────┐
      │   │         │         │
      │  end     confirm    tools
      │             │         │
      │      ┌──────┴──┐      │
      │      │ interrupt() │  │
      │      │ (pause réelle,│ │
      │      │  reprise via  │ │
      │      │  Command)     │ │
      │      └──────┬──┘      │
      │             │         │
      │     route_after_confirm │
      │             │         │
      │        ┌────┴────┐    │
      │        │         │    │
      │       end      tools ◀┘
      │                  │
      └──────────────────┘
       (retour vers agent après tool)
```

- **`agent`** : construit le prompt système (profil candidat + consignes strictes sur les URLs) et invoque le LLM avec l'ensemble des outils disponibles en conversation libre (`ALL_CHAT_TOOLS` = outils métier de l'agent + `action_query_database` + outils web). Si le LLM émet un tool call vers un outil listé dans `SENSITIVE_TOOLS`, le nœud **n'exécute rien** : il place l'action en attente (`pending_action`) et génère un message de confirmation via un appel LLM dédié (`_generate_confirmation_message`).
- **`confirm`** : si une action est en attente, ce nœud appelle `interrupt(...)` — l'exécution du graphe **s'arrête littéralement ici** et l'état est persisté (voir Checkpointer ci-dessous). Le prochain message de l'utilisateur sur ce même `chat_id` est alors interprété comme la réponse à cette confirmation (`Command(resume=user_input)`), et non comme une nouvelle requête libre. L'interprétation de la réponse (`_interpret_confirmation`) traite d'abord une liste de mots-clés explicites (oui/non/vas-y/annule/...) avant de retomber sur un appel LLM classificateur en cas de formulation ambiguë.
- **`tools`** : un `ToolNode` standard exécutant `ALL_CHAT_TOOLS`, atteint soit directement depuis `agent` (outils non sensibles : recherche BDD, recherche web, lecture de page), soit depuis `confirm` une fois l'action sensible confirmée — dans ce dernier cas, le tool call rejoué est **exactement celui généré au tour précédent** (mêmes `args`, même `id`), jamais reformulé entre-temps.

### Persistance et reprise (checkpointing)

Le graphe est compilé de deux façons distinctes selon le contexte (`create_chat_router_graph(use_local_sqlite: bool)`) :
- **En production** (Telegram, scripts, adaptateur `ChatRouter` de `src/dashboard/chat_router.py`) : compilé avec un `SqliteSaver` (fichier `checkpoints.db`), pour que l'`interrupt()` survive à un redémarrage du service — une confirmation en attente n'est jamais perdue.
- **Pour le développement / la CLI LangGraph** (`langgraph dev`) : une instance globale épurée `chat_router_app`, compilée sans checkpointer local, pour éviter tout conflit avec le checkpointer natif de l'outillage LangGraph.

Chaque conversation est isolée par `thread_id` (dérivé du `chat_id` Telegram ou du canal utilisé), ce qui permet à plusieurs conversations d'être en attente de confirmation en parallèle sans interférence.

Concrètement, `src/dashboard/chat_router.py::ChatRouter` sert d'adaptateur au-dessus du graphe : à chaque appel de `route_intent(user_input, chat_id, ...)`, il vérifie via `self.app.get_state(config)` si le thread est en pause sur un `interrupt()` (`current_state.next` non vide). Si oui, le message est envoyé comme `Command(resume=user_input)` ; sinon, c'est une nouvelle invocation classique avec un `HumanMessage`. Après exécution, il relit l'état pour détecter un nouvel interrupt (et en extraire le message de confirmation à renvoyer tel quel) ou retourne simplement le dernier message de l'IA.

### Outils web du chat (`tools_web.py`)

Deux outils étendent les capacités du Chat Router au-delà de la base de données et des actions de candidature :
- **`action_search_web`** : recherche via DuckDuckGo (`duckduckgo_search`), retourne titre/URL/extrait pour chaque résultat.
- **`action_read_web_pages`** : lit le contenu réel d'une ou plusieurs URLs (jusqu'à 5), avec une stratégie en deux temps — une extraction légère et rapide (`httpx` + `trafilatura`) est tentée en premier ; si le contenu récupéré est trop pauvre (page dynamique, rendu JS), l'outil bascule automatiquement sur un navigateur headless (`crawl4ai`/Playwright) pour les seules URLs concernées. Les URLs sont nettoyées et validées (`_sanitize_url`) avant toute requête, et le contenu extrait est tronqué à 3500 caractères par page pour rester raisonnable dans le contexte du LLM.

Le prompt système du nœud `agent` impose une consigne stricte : toute URL fournie par l'utilisateur déclenche directement `action_read_web_pages` (jamais `action_search_web`), pour éviter qu'un lien explicite ne soit ignoré au profit d'une recherche générique.

---

## 🔌 Ajouter un outil ou un connecteur

### Ajouter un nouvel outil pilotable par le LLM

1. **Implémente la logique métier** dans `src/tools/` (ex: `src/tools/mon_outil.py`), en suivant le même principe que `ats_analyzer.py` ou `cv_generator.py` : une classe ou fonction qui fait le travail, sans dépendance à LangChain.
2. **Expose-la comme `@tool`** dans `src/agent/tools.py` (outils métier) ou `src/agent/Chat_Router/tools_web.py` (outils spécifiques au chat, comme la recherche/lecture web) :
   ```python
   from src.tools.mon_outil import MonOutil

   @tool
   def action_mon_outil(param1: str, param2: int) -> str:
       """Docstring claire : c'est ce texte que le LLM lit pour décider quand
       appeler cet outil. Décris précisément ce que fait l'outil, ses paramètres
       et ce qu'il retourne."""
       resultat = MonOutil().faire_quelque_chose(param1, param2)
       return str(resultat)
   ```
3. **Ajoute-le à la liste utilisée par le superviseur autonome**, `ALL_AGENT_TOOLS` (dans `tools.py`) — c'est cette liste qui alimente à la fois `llm.bind_tools(...)` dans `decide_autonomy_node` et le `ToolNode` du sous-graphe de traitement.
4. **Ajoute-le aussi à `ALL_CHAT_TOOLS`** (dans `chat_router_graph.py`) s'il doit être disponible en conversation libre. Cette liste est volontairement indépendante d'`ALL_AGENT_TOOLS` : un outil peut être réservé au superviseur autonome, au chat, ou aux deux.
5. **Décide s'il est sensible.** Si l'outil a un effet externe irréversible (envoi de message, paiement, suppression, action sur un tiers), ajoute son nom au `set` `SENSITIVE_TOOLS` dans `chat_router_graph.py` — le nœud `agent` du Chat Router basculera alors automatiquement vers `confirm` (donc vers un `interrupt()`) avant toute exécution en conversation libre. Sans cette étape, l'outil s'exécute immédiatement dès que le LLM décide de l'appeler (c'est le comportement voulu pour les outils en lecture seule comme `action_query_database` ou les outils web).
6. **Documente-le dans les prompts système** concernés (`nodes.py::decide_autonomy_node` et/ou `chat_router_graph.py::agent_node`), pour que le LLM sache quand et comment l'utiliser — la docstring seule guide l'appel, mais les règles de zone/contexte doivent être explicites dans le prompt.

### Le cas particulier de l'automatisation navigateur (Playwright MCP)

`action_apply_via_browser` ne pilote pas directement un navigateur : il passe par `MCPPlaywrightToolkit` (`src/tools/mcp_playwright_tool.py`), qui maintient une **session MCP unique et partagée** vers le serveur `@playwright/mcp` (lancé via `npx`). Concrètement :
- La session est créée paresseusement au premier appel (`get_session()`) et réutilisée pour les appels suivants, protégée par un verrou `asyncio.Lock`.
- Chaque action navigateur (naviguer, saisir du texte, téléverser un fichier, cliquer) est un appel d'outil MCP (`browser_navigate`, `browser_type`, `browser_file_upload`, `browser_click`, etc.) exécuté via `toolkit.execute_tool(...)`.
- Le serveur MCP nécessite Node.js et le paquet `@playwright/mcp` accessible via `npx` dans l'image du conteneur `agent` (voir `GETTING_STARTED.md` pour l'installation).

### Ajouter un nouveau connecteur externe (API tierce, messagerie, etc.)

1. Crée un client dédié dans `src/connectors/` (ex: `src/connectors/mon_service_client.py`), qui encapsule l'authentification et les appels réseau — sur le modèle de `gmail_client.py`, `telegram_bot.py` ou `france_travail.py` (authentification OAuth2 avec cache de jeton). Ce client ne doit rien savoir du LLM ni du tool calling : c'est un client d'API classique.
2. Ajoute les identifiants/clés nécessaires dans `.env` et `src/config.py` (`Settings`).
3. Si le connecteur doit être pilotable par le LLM, expose une ou plusieurs méthodes du client via un `@tool`, comme pour un outil classique (voir ci-dessus).
4. Si le connecteur est un canal d'entrée (ex: un autre bot de messagerie en plus de Telegram), crée une boucle d'écoute sur le modèle de `start_telegram_listener()` dans `src/main.py`, qui instancie un `ChatRouter` (`src/dashboard/chat_router.py`) et appelle `route_intent(...)` avec un `chat_id` propre à ce canal — chaque `chat_id` devient un `thread_id` LangGraph distinct, donc chaque canal garde son propre état de conversation (y compris ses interrupts en attente) sans interférence.
5. Ajoute le service au `docker-compose.yml` si le connecteur nécessite un processus séparé (ex: un autre bot, un serveur webhook) ; sinon, s'il s'agit juste d'un client HTTP appelé depuis `agent`, aucune modification de `docker-compose.yml` n'est nécessaire.

---

## 🛡️ Résilience & sécurité

- **Fallback LLM en cascade** (Groq → Gemini → Ollama), avec propagation correcte du tool calling à chaque niveau via un wrapper `FallbackChatModel` personnalisé. Le service `ollama` du `docker-compose.yml` assure que ce dernier niveau de secours est toujours disponible localement, sans dépendance à un fournisseur externe.
- **Filtrage amont déterministe** : le routage `check_if_rejected` du sous-graphe garantit qu'une offre en Zone Rouge ne peut jamais déclencher d'appel LLM ni de tool call, quelle que soit la robustesse du prompt de décision.
- **Cache et renouvellement automatique du jeton France Travail** : `FranceTravailConnector` réutilise le jeton OAuth2 tant qu'il est valide (avec une marge de sécurité de 30 secondes) et n'en redemande un nouveau qu'en cas d'expiration, pour limiter les appels inutiles à l'endpoint d'authentification.
- **Retry automatique sur JSON malformé** pour l'analyse ATS et la génération de CV, avec distinction claire entre une erreur technique et un vrai rejet d'offre. Le Chat Router applique le même principe de robustesse à ses propres appels LLM auxiliaires (génération et interprétation de confirmation) via `_invoke_llm_with_retry`, avec repli sur une confirmation textuelle statique si le LLM échoue malgré les tentatives.
- **Backoff exponentiel** en cas de rate limit (429), avec compteur d'échecs consécutifs, visible dans les traces LangSmith si activées.
- **Garde-fou anti-blocage** : les offres restées bloquées en `PROCESSING` (crash, redémarrage) sont automatiquement remises en file au début de chaque cycle `inspect`.
- **Confirmation humaine des actions irréversibles dans le chat, via interruption réelle du graphe** : `action_send_email`, `action_apply_via_browser` et `action_reject_offer` (`SENSITIVE_TOOLS`) ne sont jamais exécutés au premier appel du LLM en conversation libre. Le nœud `confirm` suspend littéralement l'exécution via `interrupt()`, et cet état est persisté par le checkpointer SQLite : même un redémarrage du service entre la question et la réponse de l'utilisateur ne fait pas perdre la confirmation en attente. L'action rejouée après confirmation utilise systématiquement les arguments et l'`id` de tool call d'origine — jamais ceux qu'un nouvel appel du LLM pourrait reformuler entre-temps.
- **Interprétation de confirmation à deux niveaux** : une liste de mots-clés explicites (`oui`, `non`, `annule`, `vas-y`, etc.) est vérifiée en premier pour une réponse déterministe instantanée ; seule une formulation ambiguë déclenche un appel LLM classificateur dédié, qui doit répondre par un unique mot (`OUI`/`NON`).
- **Aucun statut de candidature n'est jamais menti** : `APPLIED` n'est écrit qu'après confirmation réelle du résultat de l'outil utilisé (navigateur ou e-mail).
- **Traçabilité renforcée via LangSmith** : chaque décision du LLM (y compris les tool calls invalides éventuels, et les interrupts du Chat Router) est observable a posteriori, ce qui facilite l'audit du raisonnement de l'agent sans avoir à instrumenter manuellement le code.
- **Validation et nettoyage systématique des URLs** avant toute requête HTTP dans les outils web du chat (`_sanitize_url`), pour éviter les schémas non-HTTP(S) ou les URLs malformées transmises par l'utilisateur ou générées par le LLM.

### Point d'attention : requêtage base de données

`action_query_database` accepte à la fois des filtres structurés (statut, entreprise, score, tri) **et**, si le LLM le fournit, une requête SQL brute limitée aux instructions `SELECT`. Ce n'est donc pas un accès exclusivement paramétré : la protection actuelle repose sur un contrôle de préfixe (`SELECT`) et une correction automatique de nom de table (`offers` → `jobs`), pas sur un rôle PostgreSQL restreint en lecture seule ni sur une validation de la requête elle-même. Cet outil n'étant pas dans `SENSITIVE_TOOLS` (lecture seule), il s'exécute directement depuis `agent` sans passer par `confirm`. Voir [Pistes d'évolution](#️-pistes-dévolution).

---

## 🧩 Stack technique

| Composant | Technologie |
|---|---|
| Orchestration agent | LangGraph (graphe superviseur, sous-graphe de traitement, graphe du Chat Router) |
| Persistance des conversations en attente | LangGraph Checkpointer (`SqliteSaver`) |
| Observabilité | LangSmith |
| Orchestration infra | Docker Compose |
| LLM | Groq (`gpt-oss-120b`) → Gemini 1.5 Flash → Ollama (`llama3.2`, conteneur local) |
| Framework LLM | LangChain |
| Base de données | PostgreSQL + SQLAlchemy (métier) / SQLite (checkpointing du Chat Router) |
| Automatisation navigateur | **Playwright MCP** (`@playwright/mcp`, Microsoft) via le protocole MCP |
| Recherche & lecture web (chat) | DuckDuckGo (`duckduckgo_search`), `httpx` + `trafilatura`, repli `crawl4ai` (Playwright headless) |
| Récupération des offres | **API France Travail** (OAuth2 client_credentials) |
| E-mail | Gmail API |
| Notifications & HITL | Telegram Bot API |
| Dashboard web | Streamlit |
| Tâches asynchrones | Celery |
| Génération de documents | python-docx |
| Configuration | Pydantic + YAML |

---

## 📌 Limitations connues

- Le support du tool calling par Ollama (dernier recours) dépend fortement de la version du modèle local ; en cas d'échec, l'agent retombe proprement sur `PENDING_APPROVAL` plutôt que de planter.
- L'automatisation de candidature en ligne dépend de la structure du DOM du site ciblé (via Playwright MCP), susceptible de changer sans préavis, et nécessite un serveur Node.js/`npx` fonctionnel dans le conteneur `agent`.
- Le jeton OAuth2 France Travail dépend des quotas et de la disponibilité de l'API partenaire ; un échec d'authentification bloque tout le cycle `fetch` jusqu'au prochain essai.
- `JobModel` ne possède pas de colonne `updated_at` : la détection des offres bloquées en `PROCESSING` se base sur `created_at`, ce qui est moins précis pour des blocages récents.
- En Zone Verte, le superviseur autonome postule sans validation humaine intermédiaire : la seule barrière est le seuil de score ATS configuré, pas un HITL. C'est un choix de conception assumé, à ajuster selon votre tolérance au risque via `autonomy_thresholds.zone_verte_auto_apply`.
- Le mécanisme de confirmation du chat repose, au-delà des mots-clés explicites, sur un appel LLM classificateur pour les formulations ambiguës — un risque résiduel de mauvaise interprétation de l'intention subsiste dans ces cas-là, bien que l'action rejouée utilise toujours les arguments d'origine, jamais reformulés.
- `action_query_database` autorise du SQL brut encadré (voir ci-dessus), ce qui suppose une base configurée avec un utilisateur aux droits limités si l'exposition du bot est élargie au-delà d'un usage personnel.
- Le modèle Ollama (`llama3.2`) n'est pas préchargé dans l'image : au premier lancement, il doit être téléchargé manuellement dans le conteneur (voir `GETTING_STARTED.md`), sinon la cascade de secours échouera silencieusement à ce dernier niveau.
- `process_jobs_node` traite les offres `NEW` en boucle synchrone dans une seule session DB, avec une pause fixe de 2 secondes entre chaque offre : un très gros volume d'offres allonge d'autant la durée d'un cycle `process` avant le prochain `inspect`.
- L'activation de LangSmith (`LANGCHAIN_TRACING_V2=true`) envoie les prompts et réponses du LLM — y compris potentiellement des extraits du CV, des offres, et le contenu des pages web lues par le chat — vers l'API LangSmith externe ; à garder en tête si les données traitées sont sensibles.
- Le checkpointer SQLite du Chat Router (`checkpoints.db`) est un fichier local unique : en cas de scaling horizontal du service qui héberge le bot Telegram, ce fichier doit être partagé (volume commun) ou remplacé par un checkpointer plus adapté à un environnement distribué (ex: Postgres).
- L'extraction de contenu web via `crawl4ai` (navigateur headless) est plus lente et plus coûteuse en ressources que l'extraction légère `httpx`/`trafilatura` ; elle n'est déclenchée qu'en repli, mais un grand nombre d'URLs dynamiques dans une même requête peut ralentir sensiblement la réponse du chat.

---

## 🗺️ Pistes d'évolution

- Ajout d'un rôle PostgreSQL dédié, strictement en lecture seule, pour sécuriser l'exécution du SQL brut actuellement accepté par `action_query_database`.
- Migration du checkpointer du Chat Router vers un backend adapté à un environnement multi-instances (ex: `PostgresSaver`) si le bot venait à être déployé de façon distribuée.
- Préchargement automatique du modèle Ollama au démarrage du conteneur (`entrypoint` ou service d'init dédié), pour éviter l'étape manuelle actuelle.
- Ajout d'une colonne `updated_at` sur `JobModel` pour fiabiliser la détection des offres bloquées en `PROCESSING`.
- Mise en place de tags/metadata LangSmith par offre et par thread de conversation (ex: `job_id`, zone d'autonomie, `chat_id`) pour filtrer les traces plus facilement par cas.
- Mise en cache des résultats de `action_read_web_pages` par URL, pour éviter de relire une même page plusieurs fois au sein d'une conversation.
- Garder une session MCP Playwright persistante et surveillée (health-check) plutôt que recréée à la demande, pour réduire la latence de la première candidature Zone Verte après un redémarrage.

---

## 🤝 Contribuer

Les contributions (correctifs, nouveaux outils, nouveaux connecteurs, documentation) sont bienvenues — voir [`CONTRIBUTING.md`](./CONTRIBUTING.md) pour la marche à suivre.

## 📄 Licence

Projet personnel — usage non commercial.