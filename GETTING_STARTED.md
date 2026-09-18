# 🚀 Getting Started — Job Agent AI

Ce guide permet d'installer, configurer et lancer **Job Agent AI** avec Docker Compose.

Le projet ne nécessite pas d'installation Python locale : les services applicatifs sont construits et exécutés dans des conteneurs Docker.

> 🔑 Pour obtenir chacune des clés API mentionnées ci-dessous (Groq, Gemini, France Travail, Telegram, Gmail, LangSmith), suis le guide dédié [`API_KEYS.md`](./API_KEYS.md) — il donne les liens directs et la marche à suivre pas à pas pour chaque service.

---

## 📋 Prérequis

Avant de commencer, installer :

* Docker Desktop
* Docker Compose
* Git

Sous Windows, Docker Desktop doit être configuré avec **WSL 2**.

Vérifier Docker :

```bash
docker --version
docker compose version
```

---

# 1. 📥 Cloner le projet

```bash
git clone <URL_DU_REPOSITORY>
cd job-agent-ai
```

Si le projet est déjà présent localement :

```bash
cd job-agent-ai
```

---

# 2. 🔐 Configurer les variables d'environnement

Créer un fichier `.env` à la racine du projet :

```bash
cp .env.example .env
```

Si `.env.example` n'existe pas :

```bash
touch .env
```

Puis renseigner les clés nécessaires (voir [`API_KEYS.md`](./API_KEYS.md) pour savoir où les récupérer).

Exemple :

```env
# =========================
# LLM
# =========================

GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key

# Fournisseur forcé :
# laisser vide pour utiliser le fallback automatique
# groq -> gemini -> ollama
FORCED_LLM_PROVIDER=

# =========================
# Ollama
# =========================

OLLAMA_BASE_URL=http://ollama:11434

# =========================
# Telegram
# =========================

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# =========================
# Gmail
# =========================

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# =========================
# France Travail (remplace l'ancien scraping Apify)
# =========================

FRANCETRAVAIL_CLIENT_ID=your_francetravail_client_id
FRANCETRAVAIL_CLIENT_SECRET=your_francetravail_client_secret

# =========================
# Database
# =========================

POSTGRES_DB=job_agent
POSTGRES_USER=job_agent
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=db
POSTGRES_PORT=5432

# =========================
# Chat Router (checkpointing des conversations)
# =========================

CHAT_ROUTER_DB_PATH=/app/src/agent/Chat_Router/checkpoints.db

# =========================
# Observabilité (LangSmith)
# =========================

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=job-agent-ai
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

Les noms exacts des variables doivent correspondre à celles utilisées dans `src/config.py`.

> Le bloc LangSmith est optionnel : si tu ne renseignes pas `LANGCHAIN_API_KEY` (ou que tu laisses `LANGCHAIN_TRACING_V2` vide/`false`), l'agent démarre normalement sans traçage.

> `CHAT_ROUTER_DB_PATH` est optionnel : sans cette variable, le Chat Router écrit son fichier de checkpoints à côté de `chat_router_graph.py`. Ne la surcharge que si ce fichier doit vivre sur un volume Docker monté explicitement.

> `FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET` sont obligatoires : sans eux, `FranceTravailConnector` lève une erreur au démarrage (`ValueError`) et le service `agent` ne pourra pas récupérer d'offres.

---

# 3. 📄 Vérifier les fichiers nécessaires

Avant le premier lancement, vérifier que les éléments suivants existent :

```text
job-agent-ai/
├── .env
├── config.yaml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── assets/
│   └── master_cv.docx
└── src/
```

Le CV maître :

```text
assets/master_cv.docx
```

est utilisé comme template pour générer les CV personnalisés.

---

# 4. 📦 Vérifier les dépendances Python et Node.js

Le projet utilise notamment :

```text
langchain
langgraph
langgraph-checkpoint-sqlite
langchain-groq
langchain-google-genai
langchain-openai
langsmith
mcp
langchain-mcp-adapters
pydantic
pydantic-settings
sqlalchemy
psycopg2
python-docx
streamlit
structlog
duckduckgo-search
httpx
trafilatura
crawl4ai
```

### Important : `pydantic-settings`

Le fichier `requirements.txt` doit contenir :

```text
pydantic-settings>=2.0,<3
```

Sans cette dépendance, le démarrage peut échouer avec :

```text
ModuleNotFoundError: No module named 'pydantic_settings'
```

### Important : `langsmith`

Le traçage LangSmith est piloté par LangChain via les variables d'environnement `LANGCHAIN_*` : aucune ligne de code supplémentaire n'est nécessaire dans les scripts pour l'activer, mais le paquet `langsmith` doit être présent dans `requirements.txt` :

```text
langsmith>=0.1,<1
```

Sans ce paquet, `LANGCHAIN_TRACING_V2=true` peut lever une erreur d'import au démarrage selon les versions de LangChain installées.

### Important : le serveur MCP Playwright (Node.js requis)

L'automatisation de candidature en ligne (`action_apply_via_browser`) ne s'appuie plus sur `browser-use`, mais sur le **serveur MCP Playwright de Microsoft** (`@playwright/mcp`), lancé automatiquement via `npx` par `MCPPlaywrightToolkit` (`src/tools/mcp_playwright_tool.py`).

Cela implique que l'image Docker du service `agent` doit contenir :
- **Node.js** et **npm/npx** (pour exécuter `npx -y @playwright/mcp --browser chromium`) ;
- les **dépendances système de Chromium** (le `Dockerfile` doit installer les mêmes bibliothèques que celles requises par Playwright habituellement).

Vérifier dans le `Dockerfile` qu'une étape d'installation de Node.js est présente (ex: image de base `node` en multi-stage, ou installation via le gestionnaire de paquets du système). Sans Node.js disponible dans le conteneur, `get_session()` échouera avec une erreur de type "commande `npx` introuvable".

Pour vérifier manuellement que le serveur MCP Playwright peut être lancé dans le conteneur :

```bash
docker compose exec agent npx -y @playwright/mcp --version
```

### Important : dépendances du Chat Router (outils web + checkpointing)

Le graphe du Chat Router (`src/agent/Chat_Router/`) ajoute plusieurs dépendances spécifiques :

```text
langgraph-checkpoint-sqlite   # SqliteSaver pour la persistance des interrupts
duckduckgo-search             # action_search_web
httpx                         # extraction légère de pages web
trafilatura                   # extraction du texte principal d'une page HTML
crawl4ai                      # repli navigateur headless pour les pages dynamiques (JS)
```

`crawl4ai` s'appuie sur un navigateur Chromium headless, comme le serveur MCP Playwright : après l'installation du paquet Python, un navigateur doit être disponible dans l'image (voir la documentation de `crawl4ai`/Playwright pour l'installation des binaires navigateur dans le `Dockerfile`).

Après toute modification du fichier `requirements.txt`, reconstruire l'image Docker.

---

# 5. 🐳 Construire les images

Lancer :

```bash
docker compose build
```

Pour forcer une reconstruction complète :

```bash
docker compose build --no-cache
```

Puis démarrer les services :

```bash
docker compose up -d
```

---

# 6. 🔍 Vérifier les conteneurs

```bash
docker compose ps
```

Les services principaux sont :

| Service     | Rôle                   |    Port |
| ----------- | ---------------------- | ------: |
| `db`        | PostgreSQL             |  `5432` |
| `ollama`    | LLM local              | `11434` |
| `agent`     | Superviseur + Telegram |       — |
| `dashboard` | Interface Streamlit    |  `8501` |

---

# 7. 🧠 Télécharger le modèle Ollama

Ollama est utilisé comme dernier recours de la cascade :

```text
Groq
  ↓
Gemini
  ↓
Ollama
```

Le modèle configuré par défaut est :

```text
llama3.2
```

Télécharger le modèle dans le conteneur Ollama :

```bash
docker compose exec ollama ollama pull llama3.2
```

Vérifier :

```bash
docker compose exec ollama ollama list
```

Tu dois voir :

```text
llama3.2
```

---

# 8. 🌐 Vérifier le dashboard

Le dashboard Streamlit est disponible sur :

```text
http://localhost:8501
```

Il permet notamment de visualiser l'activité de l'agent et d'utiliser le chat conversationnel.

---

# 9. 📱 Vérifier Telegram

Une fois le service `agent` démarré :

```bash
docker compose logs -f agent
```

Tu dois retrouver des messages similaires à :

```text
🚀 Démarrage de Job Agent AI...
🗄️ Base de données initialisée avec succès.
📱 Bot Telegram en cours d'écoute...
🧠 Démarrage du Superviseur Autonome LangGraph...
🟢 Agent Autonome 100% opérationnel.
```

Si tu n'as pas encore de bot/token/chat_id Telegram, crée-les d'abord via [`API_KEYS.md`](./API_KEYS.md#-telegram).

---

# 10. 🔎 Tester la récupération d'offres et comprendre le graphe superviseur

Le superviseur (`src/agent/graph.py`) fonctionne en boucle continue à quatre phases, pilotées par `state["phase"]` :

```text
inspect
   ↓
fetch
   ↓
process
   ↓
sleep
   ↓
inspect
```

- **`inspect`** recompte les offres `NEW` et remet en file toute offre bloquée en `PROCESSING` depuis plus de 15 minutes.
- **`fetch`** interroge l'**API France Travail** (authentification OAuth2 via `FranceTravailConnector`) si le stock est vide et insère les nouvelles offres en base.
- **`process`** dépile toutes les offres `NEW` une par une et invoque, pour chacune, le **sous-graphe de traitement** décrit ci-dessous.
- **`sleep`** met le superviseur en pause (1h en cycle normal, backoff exponentiel jusqu'à 15 min en cas de rate limit 429).

Chaque offre dépilée en phase `process` traverse le sous-graphe suivant (`src/agent/nodes.py` + routage dans `graph.py`) :

```text
analyze_job (score ATS)
        │
   check_if_rejected
        │
  ┌─────┴─────┐
REJECTED   QUALIFIED
  │             │
  ▼             ▼
save_job   decide_autonomy (LLM + tool calling)
                 │
           tools_condition
                 │
         ┌───────┴───────┐
   tool_calls          pas de tool_calls
         │                   │
         ▼                   ▼
       tools ───────────▶ save_job
     (ToolNode)
```

Les logs permettent de suivre chaque étape :

```text
🔍 [Étape 1/3] Début de l'analyse ATS...
✅ [Étape 1/3] Analyse ATS terminée...
🤖 [Étape 2/3] L'agent analyse l'offre...
💾 [Étape 3/3] Enregistrement...
```

Une offre en Zone Rouge saute directement de `analyze_job` à `save_job` (visible dans les logs par l'absence du message `🤖 [Étape 2/3]`) — c'est le comportement attendu du routage `check_if_rejected`, pas une anomalie.

Pour vérifier que l'authentification France Travail fonctionne (jeton obtenu avec succès), chercher dans les logs :

```text
🔑 Nouveau jeton France Travail généré
```

Si ce message n'apparaît jamais, ou qu'une erreur `❌ Erreur d'authentification France Travail` s'affiche, vérifier `FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET` et le statut de l'abonnement de l'application sur le portail France Travail Connect (voir [`API_KEYS.md`](./API_KEYS.md#-france-travail)).

---

# 11. 🎯 Comprendre les zones d'autonomie

La décision utilise trois zones.

## 🟢 Zone Verte

Score élevé.

Le LLM peut utiliser les outils pour :

```text
action_generate_cv
        ↓
action_apply_via_browser
```

ou :

```text
action_generate_cv
        ↓
action_send_email
```

La candidature est automatique selon les seuils configurés. `action_apply_via_browser` pilote le navigateur via le serveur MCP Playwright (`@playwright/mcp`), pas via un appel direct à Playwright ou browser-use. Dans le sous-graphe, ces tool calls sont exécutés par le nœud `tools` (un `ToolNode` LangGraph) avant que `save_job` ne persiste le résultat.

---

## 🟠 Zone Orange

Score intermédiaire.

Aucune candidature automatique n'est exécutée.

L'offre passe en :

```text
PENDING_APPROVAL
```

Une notification Telegram est envoyée avec des boutons permettant de décider :

```text
✅ Approuver
❌ Rejeter
```

Dans le sous-graphe, `decide_autonomy` ne produit alors aucun tool call : `tools_condition` route directement vers `save_job` sans passer par le nœud `tools`.

---

## 🔴 Zone Rouge

Score faible ou deal-breaker.

Le filtrage est **déterministe et se produit avant l'appel au LLM** : dès `analyze_job`, si le score est sous `zone_rouge_reject`, le statut `REJECTED` est fixé et le routage `check_if_rejected` envoie l'offre directement à `save_job`, sans jamais invoquer `decide_autonomy` ni le LLM.

Le statut final est :

```text
REJECTED
```

---

# 12. 🛠️ Vérifier le tool calling

Le projet utilise LangChain :

```python
llm.bind_tools(tools)
```

Pour vérifier que le LLM génère réellement des appels d'outils, ajouter temporairement un debug après l'appel du modèle :

```python
print("========== DEBUG TOOL CALL ==========")
print("TYPE:", type(response))
print("CONTENT:", response.content)
print("TOOL_CALLS:", getattr(response, "tool_calls", None))
print(
    "INVALID_TOOL_CALLS:",
    getattr(response, "invalid_tool_calls", None)
)
print(
    "ADDITIONAL_KWARGS:",
    getattr(response, "additional_kwargs", None)
)
print("====================================")
```

Un vrai appel d'outil doit apparaître dans :

```python
response.tool_calls
```

et non uniquement dans :

```python
response.content
```

### Exemple correct

```python
[
    {
        "name": "action_reject_offer",
        "args": {
            "reason": "..."
        }
    }
]
```

### Exemple incorrect

```text
{
    "tool": "action_reject_offer",
    "arguments": {
        "reason": "..."
    }
}
```

Le deuxième cas signifie que le LLM **simule** un appel d'outil dans son texte.

> Avec LangSmith activé (voir section 13 bis), ce diagnostic devient visible directement dans l'interface web, trace par trace, sans avoir à ajouter de `print` temporaires : chaque exécution du sous-graphe (ou du graphe du Chat Router) affiche le contenu exact envoyé au LLM et les tool calls réellement émis.

---

# 13. 🔄 Fallback LLM

Le système utilise trois fournisseurs :

```text
Groq
  ↓ quota/rate limit
Gemini
  ↓ échec
Ollama
```

Le provider peut être forcé avec :

```env
FORCED_LLM_PROVIDER=groq
```

ou :

```env
FORCED_LLM_PROVIDER=gemini
```

ou :

```env
FORCED_LLM_PROVIDER=ollama
```

Pour utiliser la cascade normale :

```env
FORCED_LLM_PROVIDER=
```

---

# 13 bis. 🔭 Activer et utiliser LangSmith

LangSmith permet de visualiser dans une interface web chaque trace d'exécution du graphe superviseur, du sous-graphe de traitement, et du graphe du Chat Router.

### Activation

1. Créer un compte sur [smith.langchain.com](https://smith.langchain.com) et générer une clé API (voir [`API_KEYS.md`](./API_KEYS.md#-langsmith)).
2. Ajouter dans `.env` :
   ```env
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=ta_cle_langsmith
   LANGCHAIN_PROJECT=job-agent-ai
   ```
3. Vérifier que `docker-compose.yml` propage bien ces variables au service `agent` (et à `dashboard` si le chat conversationnel doit être tracé aussi).
4. Reconstruire si `langsmith` vient d'être ajouté à `requirements.txt` :
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```
   Sinon, un simple redémarrage suffit :
   ```bash
   docker compose restart agent
   ```

### Vérifier que ça fonctionne

```bash
docker compose logs -f agent
```

Lancer un cycle complet (récupération d'offres + traitement d'au moins une offre), puis se rendre sur [smith.langchain.com](https://smith.langchain.com), ouvrir le projet `job-agent-ai` (ou le nom choisi) : une nouvelle trace doit apparaître pour chaque invocation du sous-graphe (`analyze_job` → `decide_autonomy` → éventuellement `tools` → `save_job`).

Envoyer aussi un message Telegram déclenchant une action sensible (ex: "envoie un mail à Acme") permet de voir apparaître une trace pour le graphe du Chat Router, avec le nœud `confirm` et son `interrupt()` visibles.

Si aucune trace n'apparaît :
- vérifier que `LANGCHAIN_TRACING_V2=true` est bien lu par le conteneur (`docker compose exec agent env | grep LANGCHAIN`) ;
- vérifier que la clé API n'a pas expiré ou n'a pas de restriction de projet ;
- vérifier la connectivité sortante du conteneur vers `api.smith.langchain.com`.

### Désactivation

Repasser `LANGCHAIN_TRACING_V2` à `false` (ou vider la variable) puis redémarrer `agent`. Aucune autre modification n'est nécessaire : le reste du pipeline est inchangé.

---

# 14. 🧪 Tester chaque fournisseur

Pour tester Groq :

```env
FORCED_LLM_PROVIDER=groq
```

Redémarrer :

```bash
docker compose restart agent
```

Pour Gemini :

```env
FORCED_LLM_PROVIDER=gemini
```

Puis :

```bash
docker compose restart agent
```

Pour Ollama :

```env
FORCED_LLM_PROVIDER=ollama
```

Puis :

```bash
docker compose restart agent
```

Cette méthode permet de déterminer précisément quel fournisseur produit les vrais `tool_calls`. Avec LangSmith activé, filtrer les traces par run permet de comparer directement le comportement des trois fournisseurs sur la même offre.

---

# 15. 🗄️ Vérifier PostgreSQL

Entrer dans PostgreSQL :

```bash
docker compose exec db psql \
  -U job_agent \
  -d job_agent
```

Lister les tables :

```sql
\dt
```

Quitter :

```sql
\q
```

---

# 16. 🔄 Offre bloquée en PROCESSING

Le superviseur possède un mécanisme de récupération, exécuté au début de chaque phase `inspect`.

Au démarrage, les offres restées dans :

```text
PROCESSING
```

depuis plus de 15 minutes sont automatiquement remises en `NEW`.

Un log de ce type est donc attendu après un crash ou un redémarrage :

```text
♻️ 1 offre(s) bloquée(s) en PROCESSING remises en file.
```

---

# 17. 📊 Statuts des offres

Les principaux statuts sont :

```text
NEW
PROCESSING
ANALYZED
CV_READY
PENDING_APPROVAL
APPLIED
BROWSER_FAILED
EMAIL_FAILED
REJECTED
```

Le statut `APPLIED` ne doit être écrit qu'après confirmation réelle de l'action.

---

# 18. 💬 Tester le Chat Router et sa confirmation par interruption

Le chat conversationnel repose désormais sur un graphe LangGraph avec un mécanisme d'`interrupt()` réel pour les actions sensibles. Pour le vérifier manuellement via Telegram :

1. Envoie un message qui déclenche une action sensible, par exemple :
   ```text
   envoie un mail à l'entreprise Acme pour le poste de Data Engineer
   ```
2. Le bot doit répondre par un message de confirmation généré dynamiquement, commençant par ⚠️.
3. À ce stade, le graphe est **en pause** sur le nœud `confirm` : vérifie que l'état est bien persisté en inspectant le fichier SQLite (le conteneur doit rester à jour même après un `docker compose restart agent`) :
   ```bash
   docker compose exec agent ls -la src/agent/Chat_Router/checkpoints.db
   ```
4. Réponds `oui` (ou `annule`) : le bot doit soit exécuter réellement l'action et confirmer le résultat, soit répondre `🚫 Action annulée.`.
5. Pour vérifier la résilience de l'interrupt face à un redémarrage, tu peux redémarrer `agent` juste après l'étape 2 (avant de répondre) :
   ```bash
   docker compose restart agent
   ```
   puis répondre `oui` : la confirmation doit toujours aboutir à l'exécution de l'action, preuve que l'état en attente a bien survécu au redémarrage grâce au `SqliteSaver`.

Pour tester les outils web du chat :

```text
trouve-moi des offres Data Engineer alternance à Paris
```
doit déclencher `action_search_web` (résultats DuckDuckGo), tandis que :
```text
https://exemple-offre.com/data-engineer-alternance
```
doit déclencher directement `action_read_web_pages` (jamais une recherche), conformément à la consigne stricte du prompt système sur les URLs.

Pour tester une candidature Zone Verte en ligne (`action_apply_via_browser`), vérifier dans les logs que la session MCP Playwright s'initialise correctement :

```text
⚡ Session Playwright MCP initialisée et active.
```

Si cette ligne n'apparaît jamais et qu'une erreur `❌ Échec de la connexion au serveur MCP Playwright` s'affiche à la place, voir la section 28 (diagnostic).

---

# 19. 🛑 Arrêter le projet

Pour arrêter les services :

```bash
docker compose down
```

Pour arrêter et supprimer également les volumes :

```bash
docker compose down -v
```

⚠️ Cette dernière commande supprime notamment les données persistées de PostgreSQL. Elle ne supprime pas le fichier `checkpoints.db` du Chat Router s'il n'est pas géré comme un volume Docker nommé (c'est un fichier simple sur le système de fichiers du conteneur ou d'un volume monté) ; pour repartir d'un Chat Router "propre" (sans conversations en attente), supprime-le manuellement :

```bash
docker compose exec agent rm -f src/agent/Chat_Router/checkpoints.db
docker compose restart agent
```

---

# 20. 🧹 Rebuild complet après une modification

Après modification du code Python :

```bash
docker compose restart agent dashboard
```

Après modification de `requirements.txt` (ex: ajout de `langsmith`, `crawl4ai`, `duckduckgo-search`, `mcp`) :

```bash
docker compose build --no-cache
docker compose up -d
```

Après modification du `Dockerfile` (ex: ajout de Node.js pour le serveur MCP Playwright) :

```bash
docker compose build --no-cache
docker compose up -d
```

---

# 21. 📜 Consulter les logs

Agent :

```bash
docker compose logs -f agent
```

Dashboard :

```bash
docker compose logs -f dashboard
```

Ollama :

```bash
docker compose logs -f ollama
```

PostgreSQL :

```bash
docker compose logs -f db
```

Tous les services :

```bash
docker compose logs -f
```

Pour l'historique détaillé du raisonnement du LLM offre par offre ou message par message, préférer l'interface LangSmith aux logs bruts une fois le traçage activé (section 13 bis).

---

# 22. 🧰 Ajouter un nouvel outil

Les outils pilotables par le LLM sont regroupés dans deux endroits selon leur usage :

```text
src/agent/tools.py                    # outils métier (candidature, CV, BDD, e-mail...)
src/agent/Chat_Router/tools_web.py    # outils spécifiques au chat (web)
```

Ils doivent rester des wrappers minces autour des implémentations métier.

Exemple :

```python
from langchain_core.tools import tool


@tool
def action_example(argument: str) -> str:
    """Description claire de l'action effectuée."""
    return implementation_metier(argument)
```

L'implémentation réelle doit rester dans le module approprié.

Exemple :

```text
src/tools/
├── mcp_playwright_tool.py
├── cv_generator.py
├── ats_analyzer.py
└── db_query.py
```

Puis ajouter l'outil à la liste utilisée par l'agent (superviseur autonome) :

```python
ALL_AGENT_TOOLS = [
    action_generate_cv,
    action_apply_via_browser,
    action_send_email,
    action_reject_offer,
    action_query_database,
]
```

Et/ou à la liste utilisée par le Chat Router, dans `chat_router_graph.py` :

```python
ALL_CHAT_TOOLS = list(ALL_AGENT_TOOLS) + [
    action_query_database,
    action_search_web,
    action_read_web_pages,
]
```

Si l'outil a un effet irréversible, ajoute-le également à `SENSITIVE_TOOLS` dans `chat_router_graph.py` pour qu'il passe par le nœud `confirm` (donc par un `interrupt()`) avant exécution en conversation libre.

Pour plus de détails sur l'ajout d'outils et de connecteurs, voir la section correspondante dans [`README.md`](./README.md#-ajouter-un-outil-ou-un-connecteur) et le guide [`CONTRIBUTING.md`](./CONTRIBUTING.md).

---

# 23. 🔌 Ajouter un nouveau connecteur

Pour un nouveau service externe :

```text
src/connectors/
```

Exemples existants :

```text
gmail_client.py
telegram_bot.py
france_travail.py
email_parser.py
```

Le connecteur doit gérer l'intégration technique (authentification, appels réseau), sans rien savoir du LLM.

L'outil LangChain doit ensuite fournir une interface simple au LLM.

Architecture recommandée :

```text
LLM
 ↓
LangChain @tool
 ↓
wrapper
 ↓
connector
 ↓
API externe
```

Si le connecteur est un nouveau canal d'entrée conversationnel (ex: un bot Discord ou WhatsApp), instancie un `ChatRouter` (`src/dashboard/chat_router.py`) et appelle `route_intent(user_input, chat_id=...)` avec un identifiant de conversation propre à ce canal, sur le modèle de `start_telegram_listener()` dans `src/main.py`. Le graphe LangGraph du Chat Router gère alors automatiquement l'isolation des conversations et la persistance des confirmations en attente, sans code supplémentaire de ta part.

---

# 24. 🔐 Sécurité

Ne jamais placer de secrets directement dans le code.

Utiliser :

```text
.env
```

et ne jamais committer :

```text
.env
credentials.json
tokens
API keys
cookies
sessions navigateur
src/agent/Chat_Router/checkpoints.db
```

Ajouter ces fichiers à `.gitignore`.

Cela inclut la clé `LANGCHAIN_API_KEY`, `FRANCETRAVAIL_CLIENT_SECRET` et `TELEGRAM_BOT_TOKEN` : elles donnent respectivement accès en écriture au projet LangSmith, à l'API France Travail en ton nom, et au contrôle du bot Telegram. Aucune ne doit jamais apparaître dans un commit. Le fichier `checkpoints.db` peut contenir l'historique de conversations et des arguments d'actions sensibles (adresses e-mail, contenus de messages) : à traiter avec la même prudence qu'un fichier de session ou un token.

Pour la procédure détaillée de création de chaque clé, voir [`API_KEYS.md`](./API_KEYS.md).

---

# 25. ⚠️ Mode développement

Le projet monte le code source dans les conteneurs :

```text
.:/app
```

Cela permet de modifier le code sans reconstruire systématiquement l'image.

Cependant, toute modification des dépendances nécessite un rebuild.

Pour explorer/déboguer le graphe du Chat Router avec l'outillage LangGraph (`langgraph dev`), utiliser l'instance globale épurée `chat_router_app` exportée par `chat_router_graph.py` (compilée sans checkpointer local, pour éviter tout conflit avec celui fourni par `langgraph dev`) plutôt que l'adaptateur `ChatRouter` de production.

---

# 26. 🚀 Démarrage rapide

Pour un premier lancement :

```bash
git clone <URL_DU_REPOSITORY>
cd job-agent-ai
```

Configurer :

```text
.env            # voir API_KEYS.md pour obtenir chaque clé
config.yaml
assets/master_cv.docx
```

Puis :

```bash
docker compose build
docker compose up -d
```

Télécharger Ollama :

```bash
docker compose exec ollama ollama pull llama3.2
```

Vérifier :

```bash
docker compose ps
```

Puis regarder les logs :

```bash
docker compose logs -f agent
```

Dashboard :

```text
http://localhost:8501
```

Traces LangSmith (si activé) :

```text
https://smith.langchain.com
```

---

# 27. ✅ Checklist de validation

Avant de considérer l'installation comme opérationnelle :

* [ ] Docker fonctionne
* [ ] `.env` est configuré (voir `API_KEYS.md`)
* [ ] `config.yaml` est configuré
* [ ] `assets/master_cv.docx` existe
* [ ] `pydantic-settings` est présent dans les dépendances
* [ ] `langsmith` est présent dans les dépendances (si traçage souhaité)
* [ ] `duckduckgo-search`, `httpx`, `trafilatura`, `crawl4ai` sont présents dans les dépendances
* [ ] Node.js/`npx` est disponible dans le conteneur `agent` (pour le serveur MCP Playwright)
* [ ] les images Docker sont construites
* [ ] PostgreSQL démarre
* [ ] Ollama démarre
* [ ] `llama3.2` est installé
* [ ] le service `agent` démarre
* [ ] `FRANCETRAVAIL_CLIENT_ID`/`SECRET` sont valides (log `🔑 Nouveau jeton France Travail généré`)
* [ ] Telegram fonctionne
* [ ] le dashboard est accessible
* [ ] les offres sont récupérées via l'API France Travail
* [ ] l'analyse ATS fonctionne
* [ ] une offre Zone Rouge saute bien `decide_autonomy` (pas d'appel LLM constaté)
* [ ] les statuts sont correctement enregistrés
* [ ] les offres Orange arrivent en validation humaine
* [ ] un test Vert produit de vrais `tool_calls` et une session MCP Playwright s'initialise
* [ ] le fallback Groq → Gemini → Ollama fonctionne
* [ ] une action sensible en chat déclenche bien une confirmation (`interrupt()`) avant exécution
* [ ] la confirmation en attente survit à un redémarrage du service `agent`
* [ ] une URL envoyée en chat déclenche `action_read_web_pages` (et non une recherche)
* [ ] les traces apparaissent dans LangSmith (si activé)

---

# 28. 🐛 Diagnostic rapide

### `ModuleNotFoundError: No module named 'pydantic_settings'`

Ajouter :

```text
pydantic-settings>=2.0,<3
```

dans `requirements.txt`, puis :

```bash
docker compose build --no-cache
docker compose up -d
```

---

### `ModuleNotFoundError: No module named 'langsmith'` (ou erreur au démarrage avec `LANGCHAIN_TRACING_V2=true`)

Ajouter :

```text
langsmith>=0.1,<1
```

dans `requirements.txt`, puis rebuild :

```bash
docker compose build --no-cache
docker compose up -d
```

Si le problème persiste sans vouloir dépendre de LangSmith immédiatement, repasser `LANGCHAIN_TRACING_V2=false` (ou vider la variable) le temps de corriger les dépendances.

---

### `ModuleNotFoundError` pour `duckduckgo_search`, `trafilatura`, `crawl4ai` ou `mcp`

Vérifier leur présence dans `requirements.txt`, puis rebuild complet :

```bash
docker compose build --no-cache
docker compose up -d
```

Si `crawl4ai` échoue à l'exécution (pas seulement à l'import) avec une erreur liée à un navigateur manquant, vérifier que les binaires navigateur headless sont bien installés dans l'image.

---

### `❌ Échec de la connexion au serveur MCP Playwright` (candidature Zone Verte)

Cette erreur, levée par `MCPPlaywrightToolkit.get_session()`, signifie généralement que :
- Node.js/`npx` n'est pas installé dans le conteneur `agent` — vérifier avec `docker compose exec agent node --version` et `docker compose exec agent npx --version` ;
- ou que le paquet `@playwright/mcp` n'a pas pu être téléchargé (pas de connectivité sortante vers le registre npm) ;
- ou que les dépendances système de Chromium manquent dans l'image.

Tester manuellement dans le conteneur :

```bash
docker compose exec agent npx -y @playwright/mcp --browser chromium --version
```

Si la commande échoue, corriger le `Dockerfile` (ajout de Node.js et des dépendances Chromium) puis rebuild complet.

---

### `ValueError: FRANCETRAVAIL_CLIENT_ID ou FRANCETRAVAIL_CLIENT_SECRET absent de la configuration`

Cette erreur est levée dès l'instanciation de `FranceTravailConnector` si les variables sont manquantes. Vérifier :

```bash
docker compose exec agent env | grep FRANCETRAVAIL
```

et renseigner les deux variables dans `.env` (voir [`API_KEYS.md`](./API_KEYS.md#-france-travail) pour les obtenir), puis :

```bash
docker compose restart agent
```

---

### `❌ Erreur d'authentification France Travail` dans les logs

Cause la plus fréquente : identifiants invalides, application non abonnée aux bons scopes (`api_offresdemploiv2 o2dsoffre`), ou application non encore activée côté portail France Travail Connect (le délai d'activation peut prendre quelques minutes après création). Revérifier la configuration de l'application sur le portail, puis redémarrer `agent`.

---

### Aucune trace n'apparaît dans LangSmith

Vérifier que les variables sont bien injectées dans le conteneur :

```bash
docker compose exec agent env | grep LANGCHAIN
```

Vérifier la validité de la clé API sur [smith.langchain.com](https://smith.langchain.com), et que le nom de projet dans `LANGCHAIN_PROJECT` correspond bien à un projet existant (LangSmith le crée automatiquement au premier run sinon).

---

### Le dashboard ne démarre pas

Consulter :

```bash
docker compose logs dashboard
```

---

### Le bot Telegram ne répond pas

Vérifier :

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Puis :

```bash
docker compose restart agent
```

---

### Une confirmation en chat ne redémarre jamais après "oui"

Vérifier que le graphe est bien compilé avec `use_local_sqlite=True` côté production (`src/dashboard/chat_router.py::ChatRouter.__init__`), et que `CHAT_ROUTER_DB_PATH` (ou le chemin par défaut) est bien accessible en écriture dans le conteneur. Vérifier aussi, via `docker compose exec agent env | grep CHAT_ROUTER`, que la variable pointe vers un chemin cohérent si elle est surchargée. Un `current_state.next` toujours vide après un `Command(resume=...)` peut indiquer que le `thread_id` utilisé pour reprendre ne correspond pas à celui utilisé pour la question initiale (vérifier la construction de `chat_id` dans `src/main.py`).

---

### Ollama ne répond pas

Vérifier :

```bash
docker compose ps
docker compose logs ollama
```

Puis :

```bash
docker compose exec ollama ollama list
```

---

### Le LLM écrit un JSON au lieu d'appeler un outil

Vérifier :

```python
response.tool_calls
```

Si la liste est vide mais que `response.content` contient :

```json
{
  "tool": "...",
  "arguments": {}
}
```

le modèle a simulé le tool call au lieu d'utiliser le mécanisme natif.

Tester chaque provider séparément avec :

```env
FORCED_LLM_PROVIDER=groq
```

puis :

```env
FORCED_LLM_PROVIDER=gemini
```

puis :

```env
FORCED_LLM_PROVIDER=ollama
```

Avec LangSmith activé, comparer directement les traces des trois providers sur la même offre permet d'identifier plus vite lequel simule ses tool calls.

---

### Une offre Zone Rouge déclenche quand même un appel LLM

Vérifier dans `src/agent/nodes.py::analyze_job_node` que le score calculé est bien inférieur à `zone_rouge_reject`, et dans `src/agent/graph.py::check_if_rejected` que `state["status"] == "REJECTED"` est bien fixé par `analyze_job_node` avant ce routage. Un score correct mais un statut resté à `"QUALIFIED"` indique un problème dans la logique de seuil de `analyze_job_node`, pas dans le routage lui-même.

---

# 29. 🧭 Architecture générale

```text
                    ┌──────────────────┐
                    │  API France      │
                    │  Travail (OAuth2)│
                    └─────────┬────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Job Fetcher   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   ATS Analyzer  │
                    └────────┬────────┘
                             │
                    check_if_rejected
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                │                ▼
          RED                │              GREEN/ORANGE
            │                │                │
            ▼                │        ┌───────┴────────┐
         Reject              │        │ LLM Supervisor │
      (save_job direct)      │        └───────┬────────┘
                             │        ┌───────┴───────┐
                             │        │               │
                             │        ▼               ▼
                             │     ORANGE           GREEN
                             │        │               │
                             │        ▼               ▼
                             │     HITL          Tool Calling
                             │        │               │
                             │        ▼               ▼
                               │    Telegram       CV + Apply
                               │                        │
                               │         ┌──────────────┴──────────────┐
                               │         │                             │
                               │         ▼                             ▼
                               │  Playwright MCP                    Gmail
                               │  (@playwright/mcp)
                               │
                               └──────────────▶ (traçage optionnel : LangSmith)

        ─────────────────────── Canal parallèle : Chat Router ───────────────────────

                    ┌─────────────────┐
        Telegram /  │      agent      │◀────────────┐
        Dashboard ─▶│  (LLM + tools)  │              │
                    └────────┬────────┘              │
                             │                        │
                    route_after_agent                 │
                    ┌────────┼────────┐               │
                    ▼        ▼        ▼               │
                  end     confirm   tools ────────────┘
                             │      (BDD, web)
                       interrupt()
                    (persisté SQLite)
                             │
                     réponse utilisateur
                             │
                    route_after_confirm
                    ┌────────┴────────┐
                    ▼                 ▼
                  end               tools (action sensible confirmée)
```

---

## 🎉 Fin

Une fois toutes les cases de la checklist validées, Job Agent AI est prêt à fonctionner en mode autonome.

Pour modifier le comportement métier, commencer par :

```text
config.yaml
```

Pour modifier le raisonnement, le routage du graphe superviseur ou les tool calls :

```text
src/agent/graph.py
src/agent/nodes.py
src/agent/tools.py
src/llm_client.py
```

Pour modifier le comportement du chat conversationnel :

```text
src/agent/Chat_Router/chat_router_graph.py
src/agent/Chat_Router/chat_state.py
src/agent/Chat_Router/tools_web.py
src/dashboard/chat_router.py
```

Pour modifier les intégrations externes :

```text
src/connectors/
src/tools/
```

Pour l'observabilité :

```text
Variables LANGCHAIN_* dans .env
https://smith.langchain.com
```

Pour obtenir de nouvelles clés API ou comprendre celles déjà en place, voir [`API_KEYS.md`](./API_KEYS.md).

Pour contribuer au projet, voir [`CONTRIBUTING.md`](./CONTRIBUTING.md).