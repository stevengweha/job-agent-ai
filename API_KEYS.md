# 🔑 API_KEYS — Obtenir toutes les clés nécessaires

Ce guide liste, service par service, comment obtenir chaque clé/identifiant utilisé dans le fichier `.env` du projet. Suis-le avant ou pendant l'étape 2 de [`GETTING_STARTED.md`](./GETTING_STARTED.md).

Récapitulatif des variables couvertes :

```text
GROQ_API_KEY
GOOGLE_API_KEY                (Gemini)
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET   (Gmail)
FRANCETRAVAIL_CLIENT_ID / FRANCETRAVAIL_CLIENT_SECRET
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
LANGCHAIN_API_KEY             (LangSmith)
```

---

## 🟢 Groq

Utilisé comme premier fournisseur LLM de la cascade (Groq → Gemini → Ollama).

1. Créer un compte sur [console.groq.com](https://console.groq.com).
2. Aller dans **API Keys** (menu de gauche).
3. Cliquer sur **Create API Key**, lui donner un nom (ex: `job-agent-ai`).
4. Copier la clé affichée **immédiatement** (elle ne sera plus visible ensuite).
5. Renseigner dans `.env` :
   ```env
   GROQ_API_KEY=gsk_...
   ```

Le plan gratuit de Groq suffit largement pour démarrer et tester le projet.

---

## 🔵 Google Gemini (`GOOGLE_API_KEY`)

Utilisé comme deuxième fournisseur LLM de la cascade.

1. Se rendre sur [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Se connecter avec un compte Google.
3. Cliquer sur **Create API key** (choisir ou créer un projet Google Cloud associé si demandé).
4. Copier la clé générée.
5. Renseigner dans `.env` :
   ```env
   GOOGLE_API_KEY=AIza...
   ```

> Cette clé (Gemini/AI Studio) est différente de `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (Gmail) ci-dessous — les deux passent par des portails Google différents.

---

## 📧 Gmail (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` + `credentials.json`)

Utilisé par `GmailClient` pour envoyer les e-mails de candidature (et par `GmailFetcher` pour lire les réponses des recruteurs).

1. Aller sur [console.cloud.google.com](https://console.cloud.google.com) et créer un nouveau projet (ou en réutiliser un).
2. Dans le menu, ouvrir **API et services → Bibliothèque**, rechercher **Gmail API**, cliquer sur **Activer**.
3. Aller dans **API et services → Écran de consentement OAuth** :
   - Type d'utilisateur : **Externe** (sauf si tu as un compte Google Workspace dédié) ;
   - Renseigner un nom d'application et un e-mail de contact ;
   - Ajouter ton propre compte Gmail comme **utilisateur de test** (obligatoire tant que l'app n'est pas publiée).
4. Aller dans **API et services → Identifiants** :
   - Cliquer sur **Créer des identifiants → ID client OAuth** ;
   - Type d'application : **Application de bureau** ;
   - Télécharger le fichier JSON généré et le renommer `credentials.json` à la racine du projet (il est déjà listé comme non versionné dans `.gitignore`).
5. Depuis ce fichier `credentials.json`, récupérer `client_id` et `client_secret` pour les reporter aussi en variables d'environnement si le code du connecteur les lit ainsi :
   ```env
   GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=xxxxx
   ```
6. Au premier envoi d'e-mail réel (`action_send_email` ou `action_send_custom_email`), le connecteur ouvre normalement un flux OAuth dans un navigateur pour autoriser l'accès à ta boîte Gmail ; le jeton obtenu est ensuite stocké selon `GMAIL_TOKEN_PATH` (par défaut `token.json`) pour ne plus redemander l'autorisation à chaque envoi.

> Comme le service `agent` tourne dans un conteneur sans navigateur graphique, effectue si besoin cette autorisation initiale une seule fois en local (hors Docker, ou via un port forwarding), puis copie le `token.json` généré dans le projet avant de (re)lancer `docker compose up`.

---

## 🇫🇷 France Travail (`FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET`)

Remplace l'ancien scraping Apify : le projet récupère désormais les offres directement via l'**API officielle France Travail** (anciennement Pôle Emploi), avec une authentification OAuth2 `client_credentials`.

1. Créer un compte sur [francetravail.io](https://francetravail.io) (portail développeur "France Travail Connect").
2. Une fois connecté, aller dans **Mes applications** (ou **Créer une application**).
3. Créer une nouvelle application, en lui donnant un nom (ex: `job-agent-ai`).
4. Dans la configuration de l'application, **s'abonner aux API nécessaires** :
   - **Offres d'emploi v2** (`api_offresdemploiv2`) ;
   - **Recherche d'offres** (scope `o2dsoffre`).
   Ce sont les deux scopes déjà utilisés par `FranceTravailConnector` (`scope: "api_offresdemploiv2 o2dsoffre"`).
5. Une fois l'application créée, récupérer l'**Identifiant client** et la **Clé secrète** affichés dans les paramètres de l'application.
6. Renseigner dans `.env` :
   ```env
   FRANCETRAVAIL_CLIENT_ID=ton_identifiant_client
   FRANCETRAVAIL_CLIENT_SECRET=ta_cle_secrete
   ```

> L'activation d'une nouvelle application peut prendre quelques minutes côté France Travail. Si l'agent renvoie une erreur d'authentification juste après la création de l'application, patiente un peu puis relance (`docker compose restart agent`).

> Ces identifiants sont utilisés par `FranceTravailConnector.get_valid_token()` pour obtenir un jeton via `https://entreprise.francetravail.fr/connexion/oauth2/access_token`, avec mise en cache automatique jusqu'à expiration (marge de sécurité de 30 secondes).

---

## 📱 Telegram (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`)

Le bot Telegram est le canal principal de notification et de HITL (boutons Approuver/Rejeter, chat conversationnel).

### Créer le bot avec BotFather

1. Ouvrir Telegram et chercher le compte officiel **[@BotFather](https://t.me/BotFather)**.
2. Lui envoyer la commande :
   ```text
   /newbot
   ```
3. Choisir un **nom d'affichage** pour le bot (ex: `Job Agent AI`).
4. Choisir un **nom d'utilisateur** unique se terminant par `bot` (ex: `job_agent_ai_bot`).
5. BotFather renvoie un message contenant le token, sous la forme :
   ```text
   123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   C'est la valeur de :
   ```env
   TELEGRAM_BOT_TOKEN=123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. (Optionnel) Personnaliser le bot avec BotFather :
   - `/setdescription` — description affichée dans le profil du bot ;
   - `/setuserpic` — photo de profil du bot.

### Récupérer son `chat_id`

1. Dans Telegram, démarrer une conversation avec ton nouveau bot (chercher son nom d'utilisateur, cliquer sur **Démarrer**/`/start`).
2. Envoyer n'importe quel message au bot (ex: `bonjour`).
3. Ouvrir dans un navigateur (en remplaçant `<TOKEN>` par le token obtenu à l'étape précédente) :
   ```text
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. Dans la réponse JSON, repérer le champ :
   ```json
   "chat": { "id": 987654321, ... }
   ```
5. Renseigner dans `.env` :
   ```env
   TELEGRAM_CHAT_ID=987654321
   ```

> Si la réponse de `getUpdates` est vide (`"result": []`), renvoie un nouveau message au bot puis rafraîchis la page — Telegram ne conserve les mises à jour non lues que temporairement.

Une fois `docker compose restart agent` effectué, le bot doit se mettre à écouter (voir la section 9 de `GETTING_STARTED.md`) et tu peux commencer à lui parler directement (`où en est ma candidature chez Google ?`, etc.).

---

## 🔭 LangSmith (`LANGCHAIN_API_KEY`)

Optionnel, mais recommandé pour observer le raisonnement du LLM (voir section 13 bis de `GETTING_STARTED.md`).

1. Créer un compte sur [smith.langchain.com](https://smith.langchain.com).
2. Créer un nouveau projet (ou utiliser celui par défaut), et note son nom exact pour `LANGCHAIN_PROJECT`.
3. Aller dans les paramètres du compte (icône profil → **Settings** → **API Keys**).
4. Cliquer sur **Create API Key**, lui donner un nom, puis copier la clé générée (elle ne sera affichée qu'une fois).
5. Renseigner dans `.env` :
   ```env
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=lsv2_...
   LANGCHAIN_PROJECT=job-agent-ai
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   ```

Cette clé donne un accès en écriture au projet LangSmith correspondant : elle ne doit jamais être partagée ni committée (voir la section Sécurité de `GETTING_STARTED.md`).

---

## ✅ Récapitulatif : où trouver quoi

| Variable | Où l'obtenir |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys |
| `GOOGLE_API_KEY` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | [console.cloud.google.com](https://console.cloud.google.com) → Identifiants OAuth (+ `credentials.json`) |
| `FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET` | [francetravail.io](https://francetravail.io) → Mes applications |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) sur Telegram, `/newbot` |
| `TELEGRAM_CHAT_ID` | `https://api.telegram.org/bot<TOKEN>/getUpdates` après un premier message au bot |
| `LANGCHAIN_API_KEY` | [smith.langchain.com](https://smith.langchain.com) → Settings → API Keys |

Une fois toutes les clés renseignées dans `.env`, reprends l'installation à partir de l'étape 3 de [`GETTING_STARTED.md`](./GETTING_STARTED.md).