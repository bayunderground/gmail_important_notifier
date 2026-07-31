# Setup Guide — GmailImportantNotifier

How to obtain every value needed in `.env`.

---

## 1. Telegram Bot Token + Chat ID

### Bot Token

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts — pick a name and username
4. BotFather replies with a token like `690461404:AAEV_P1boHkqSM1vkn3BGjl7jCknh1p-Smk`
5. Set `TELEGRAM_BOT_TOKEN=` in `.env` to this value

### Chat ID

1. Open your bot in Telegram (search for its username) and send any message
2. Open this URL in a browser (replace `<BOT_TOKEN>` with your actual token):

   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```

3. Look for `"chat":{"id":123456789}` in the JSON response
4. Set `TELEGRAM_CHAT_ID=` in `.env` to that number

---

## 2. DATABASE_URL (Neon PostgreSQL)

1. Go to **https://console.neon.tech**
2. Create a project (or use existing)
3. Go to **Dashboard** → click **Connection Details**
4. Copy the **PostgreSQL connection string** — it looks like:

   ```
   postgresql://neondb_owner:password@ep-xxx-region.aws.neon.tech/dbname?sslmode=require
   ```

5. Make sure the database name is `gmail_important_notifier` (create it if needed under **Databases** tab)
6. Set `DATABASE_URL=` in `.env` to the full connection string

---

## 3. Gmail OAuth (Client ID, Client Secret, Refresh Token)

### 3a. Create OAuth Consent Screen

1. Go to **https://console.cloud.google.com/apis/credentials/consent**
   - If you only see metrics, go to **https://console.cloud.google.com/apis/credentials** and click the **"OAuth consent screen"** tab
2. Click **Get Started**
3. Fill in:
   - App name: `GmailImportantNotifier`
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue**
5. Scopes → **Add or Remove Scopes** → search for `gmail.metadata` → check it → **Update** → **Save and Continue**
6. Test users → **Add Users** → type your Gmail address → **Add** → **Save and Continue**

### 3b. Create OAuth Client ID

1. Go to **https://console.cloud.google.com/apis/credentials**
2. Click **"+ Create Credentials"** → **OAuth client ID**
3. Application type: **Desktop app** (NOT "Web application")
4. Name: `GmailImportantNotifier`
5. Click **Create**
6. Click **Download JSON** → save the file as `client_secret.json` in the project root

### 3c. Get Refresh Token

```bash
source .venv/bin/activate
pip install google-auth-oauthlib
python get_refresh_token.py
```

1. A browser window opens → sign in with your Google account
2. Click **Allow** (or **Advanced** → **Go to GmailImportantNotifier (unsafe)**)
3. The terminal prints something like:

   ```
   GMAIL_OAUTH_REFRESH_TOKEN=1//0abcDEFghijklMNOpqrsTUVwxyz0123456789-AAAAAAAAAAAAAAAAAAAA
   ```

4. Copy that value

### 3d. Extract values from `client_secret.json`

Open `client_secret.json` — it's a JSON file with this structure:

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "client_secret": "YOUR_CLIENT_SECRET",
    ...
  }
}
```

- `GMAIL_OAUTH_CLIENT_ID` = the `client_id` value
- `GMAIL_OAUTH_CLIENT_SECRET` = the `client_secret` value

### 3e. Set in `.env`

```
GMAIL_OAUTH_CLIENT_ID=185391544609-XXXXXXXXXX.apps.googleusercontent.com
GMAIL_OAUTH_CLIENT_SECRET=GOCSPX-XXXXXXXXXX
GMAIL_OAUTH_REFRESH_TOKEN=1//YOUR_REFRESH_TOKEN_HERE
```

---

## 4. Pub/Sub (Topic + Audience)

### Prerequisites

Enable APIs:
1. Go to **https://console.cloud.google.com/apis/library**
2. Search **"Gmail API"** → **Enable**
3. Search **"Cloud Pub/Sub API"** → **Enable**

### 4a. Create Topic

1. Go to **https://console.cloud.google.com/cloudpubsub/topic/list**
2. Click **"+ Create Topic"**
3. Topic ID: `gmail-important-notifiers`
4. Click **Create**

### 4b. Grant Gmail access to publish

1. On the topic page, go to **Permissions** tab
2. Click **"+ Add Principal"**
3. Principal: `gmail-api-push@system.gserviceaccount.com`
4. Role: **Pub/Sub Publisher**
5. Click **Save**

### 4c. Create Service Account for push auth

1. Go to **https://console.cloud.google.com/iam-admin/serviceaccounts**
2. Click **"+ Create Service Account"**
3. Name: `pubsub-push-auth`
4. Click **Create and Continue** → skip roles → **Done**

### 4d. Create Push Subscription

1. Go to **https://console.cloud.google.com/cloudpubsub/subscription/list**
2. Click **"+ Create Subscription"**
3. Subscription ID: `gmail-important-notifications-sub`
4. Topic: `gmail-important-notifiers`
5. Delivery type: **Push**
6. Endpoint URL: `https://gmail-important-notifier.appspot.com/tasks/gmail-push`
7. Expand **Authentication**:
   - Check **Enable authentication**
   - Service account: `pubsub-push-auth`
   - Audience: `https://gmail-important-notifier.appspot.com/tasks/gmail-push`
8. Click **Create**

### 4e. Set in `.env`

```
PUBSUB_TOPIC_NAME=gmail-important-notifiers
PUBSUB_PUSH_AUDIENCE=https://gmail-important-notifier.appspot.com/tasks/gmail-push
```

---

## 5. Complete `.env` Example

```
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
TELEGRAM_CHAT_ID=123456789
DATABASE_URL=postgresql://neondb_owner:password@ep-xxx.region.aws.neon.tech/gmail_important_notifier?sslmode=require
GMAIL_OAUTH_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
GMAIL_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET
GMAIL_OAUTH_REFRESH_TOKEN=1//YOUR_REFRESH_TOKEN_HERE
PUBSUB_TOPIC_NAME=gmail-important-notifiers
PUBSUB_PUSH_AUDIENCE=https://gmail-important-notifier.appspot.com/tasks/gmail-push
NOTIFICATION_RETRY_AFTER_SECONDS=300
WATCH_RENEWAL_SAFETY_WINDOW_SECONDS=86400
LOG_LEVEL=INFO
```

---

## 6. Verify Everything Works

```bash
source .venv/bin/activate
python test.py
```

Expected output:
```
Testing Gmail API connectivity... OK — your-email@gmail.com
Testing Telegram bot... OK — @your_bot_username
Sending test message... OK

All tests passed.
```

---

## 7. Deploy

```bash
./depl.sh
```

Your app will be live at `https://gmail-important-notifier.appspot.com`.
