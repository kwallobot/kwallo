# Kwallo automation: one-time setup

**Time needed:** about 1 to 1.5 hours, once. Everything is done in a web browser.

> The bucket, database, Worker and GitHub project keep their internal name `pitchlab`: nobody outside sees them, so they don't need renaming.

## How the pieces fit together

| Piece | Job | Cost |
|---|---|---|
| **GitHub** (a private project) | Runs the model on a schedule: weekly full run (Monday 03:00 UTC), daily refresh (05:00 UTC), and lineup-time runs | Free (2,000 minutes a month on private projects) |
| **Cloudflare R2** (storage) | Holds all the data (what used to live in your Drive `football` folder) and the public data files for the site | Free up to 10 GB |
| **Cloudflare Worker + D1** | Answers **@kwalloAI_bot**, stores followers (chat IDs and choices only), and starts a lineup-time run about 70 minutes before kickoffs | Free |
| **Telegram** | Delivers the alerts | Free |

Keys and passwords live only in GitHub's and Cloudflare's secret settings, never in the code.

---

## Step 1: Create the accounts
1. **GitHub:** sign up at github.com (free).
2. **Cloudflare:** sign up at dash.cloudflare.com (free). To switch on R2 storage, Cloudflare may ask for a payment card even though our usage stays inside the free allowance.

## Step 2: Create the storage (R2)
1. In Cloudflare: **R2 Object Storage → Create bucket**. Name it **`pitchlab`**.
2. **R2 → Manage API tokens → Create API token:** permission **Object Read & Write**, limited to the `pitchlab` bucket. Copy and keep safe:
   - **Access Key ID**, **Secret Access Key**
   - your **Account ID** (shown on the R2 overview page)

## Step 3: Copy your data from Google Drive into R2
1. In Colab, open the 🔑 **Secrets** panel and add: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET` = `pitchlab`. Switch on notebook access for each.
2. Paste the contents of **`tools/move_drive_to_r2.py`** into a new Colab cell and run it. It copies everything in your `football` folder (it may take 10 to 30 minutes). Your Drive copy stays as a backup.

## Step 4: Create the bot's database (D1)
1. In Cloudflare: **Storage & Databases → D1 → Create database**, named **`pitchlab`**.
2. Open it, go to **Console**, paste the contents of **`worker/schema.sql`**, and run it.

## Step 5: Create the Worker (the bot's home)
1. **Workers & Pages → Create → Create Worker**, name it **`pitchlab-bot`**, **Deploy**.
2. **Edit code:** replace everything with the contents of **`worker/worker.js`**, then **Deploy**.
3. **Settings → Bindings → Add:**
   - **D1 database:** variable name `DB` → the `pitchlab` database
   - **R2 bucket:** variable name `DATA` → the `pitchlab` bucket
4. **Settings → Variables and Secrets:**
   - Text variable `GITHUB_REPO` = `your-github-username/pitchlab`
   - **Secret** `TELEGRAM_BOT_TOKEN` = your bot token from BotFather
   - **Secret** `WEBHOOK_SECRET` = a long random string you make up (letters and digits)
   - **Secret** `PIPELINE_KEY` = another long random string you make up
   - **Secret** `GITHUB_TOKEN` = from Step 7 (come back and add it then)
5. **Settings → Triggers → Cron Triggers → Add:** `*/15 * * * *` (every 15 minutes).
6. Note the Worker's address, e.g. `https://pitchlab-bot.yourname.workers.dev`.

## Step 6: Connect Telegram to the Worker
In your browser, open this address, replacing the three parts in capitals (one line, no spaces):
```
https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=https://YOUR-WORKER-ADDRESS/telegram&secret_token=YOUR_WEBHOOK_SECRET
```
It should reply `"ok":true`. Then message **@kwalloAI_bot** with `/start`: it should answer.

## Step 7: Put the project on GitHub
1. GitHub: **New repository** → name **`pitchlab`** → **Private** → Create.
2. **Add file → Upload files:** drag in everything from the unzipped `pitchlab` folder, **including the `.github` folder** (on a Mac, press Cmd+Shift+. in Finder to see it). **Commit changes.**
3. **Settings → Secrets and variables → Actions → New repository secret**, one at a time:
   `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` (= `pitchlab`), `BSD_KEY`, `PITCHAPI_KEY`,
   `TELEGRAM_BOT_TOKEN`, `WORKER_URL` (the Worker address from Step 5), `PIPELINE_KEY` (the same string as in Step 5).
4. **The Worker's GitHub token:** your profile picture → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Repository access: **only `pitchlab`**. Permissions: **Actions: Read and write**. Copy it into the Worker's `GITHUB_TOKEN` secret (Step 5.4).

## Step 8: First run
1. GitHub → your `pitchlab` project → **Actions** tab → **Weekly full run** → **Run workflow**.
2. It takes about 60 to 80 minutes. Open the run to watch progress; it should end with **"Finished"**.
3. Then in Telegram: `/follow Arsenal` (or any team), `/list`, `/settings`.

From then on, everything runs by itself: the weekly full run, the daily refresh, lineup-time runs before kickoffs, and alerts to followers.

---

## Good to know

**GitHub minutes:** a private project gets 2,000 free minutes a month. Expected use: weekly runs ~300, daily runs ~500 to 700, lineup-time runs ~600 to 900 (one per kickoff time, not per match). If you get close to the limit, the simplest fixes are making the daily refresh every other day, or making the project **public** (unlimited minutes, but anyone could read the code; your keys stay secret either way).

**Colab is still useful** for exploring and testing changes, but the automated setup now keeps the data up to date in R2. If you run the notebook in Colab, it uses your old Drive copy, which no longer gets updated automatically.

**If a run fails:** open it in the Actions tab; the log names the section that failed. The site and bot keep the previous data until the next successful run. Send me the error.

**If a key ever leaks:** create a new one (BotFather `/revoke` for the bot token, a new R2 token, a new GitHub token) and update the secret.

---

## Backups and restoring (v29)

After each **weekly full run**, everything in `data/` is copied to **`backups/YYYY-MM-DD/`** in the same bucket (inside Cloudflare, so it's quick and free). The last **4 weekly** backups are kept, plus the **first backup of each of the last 6 months**; older ones are removed automatically. The public `site/` files aren't backed up, because every run rebuilds them. The bot's followers live in D1, which Cloudflare protects separately (D1 → your database → **Time Travel** restores it to any point in the last 30 days).

**To restore** (only if something has gone badly wrong; ask Claude first):
1. Pause the schedules: GitHub → **Actions** → each workflow → **⋯ → Disable workflow**.
2. In Colab, run this (with your R2 secrets set), choosing the backup date:
   ```python
   !pip -q install boto3
   import boto3
   from google.colab import userdata
   DATE = "2026-10-26"          # the backup to restore
   s3 = boto3.client("s3", endpoint_url=f"https://{userdata.get('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                     aws_access_key_id=userdata.get("R2_ACCESS_KEY_ID"), aws_secret_access_key=userdata.get("R2_SECRET_ACCESS_KEY"), region_name="auto")
   b, n = userdata.get("R2_BUCKET"), 0
   for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=f"backups/{DATE}/"):
       for o in page.get("Contents", []):
           s3.copy_object(Bucket=b, Key="data/" + o["Key"].split("/", 2)[2], CopySource={"Bucket": b, "Key": o["Key"]}); n += 1
   print(f"Restored {n} files from {DATE}.")
   ```
3. Re-enable the workflows and start a **Weekly full run**.


## The public channel (v30)

The runs post to **@kwallo_official** by default (the bot must be an administrator there with "Post Messages"). To use a different channel, add a GitHub **variable** (not a secret): project → Settings → Secrets and variables → Actions → **Variables** tab → `TELEGRAM_CHANNEL` = `@yourchannel`.


## v31: live alerts, /stats and the premium switch

1. **Cloudflare → your Worker → Settings → Trigger Events:** change the cron from `*/15 * * * *` to **`* * * * *`** (every minute). The Worker now checks followed matches every minute, and still starts lineup-time runs every 15 minutes.
2. **/stats:** send `/stats` to the bot once. It replies with your chat ID; add it as a Worker **secret** named `ADMIN_CHAT_ID`, then `/stats` shows your figures (only to you).
3. **The premium switch:** nothing to do until premium launches. On launch day, add a GitHub **variable** `PREMIUM_ENABLED` = `1` (Settings → Secrets and variables → Actions → Variables). Free alerts then carry basic chances only, and the morning digest shows one non-top pick per match.
