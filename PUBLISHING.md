# Publishing & weekly automation

This puts the project on GitHub, publishes the site for free at
`https://<your-username>.github.io/ais-hiring-snapshot/`, and sets it to
**collect a fresh snapshot automatically every week**.

You only do steps 1–4 once. After that it runs itself.

---

## What you need

- A free GitHub account — sign up at <https://github.com> if you don't have one.
- **GitHub Desktop** (the app, no command line needed) — <https://desktop.github.com>.
  Install it and sign in with your GitHub account.

*(Prefer the command line? Skip to "Alternative: command line" at the bottom.)*

---

## Step 1 — Create an empty repository on GitHub

1. Go to <https://github.com/new>.
2. **Repository name:** `ais-hiring-snapshot`.
3. Set it to **Public** (required for free hosting, and the point is that the
   data and code are open).
4. Do **not** add a README, .gitignore, or license — the folder already has them.
5. Click **Create repository**. Leave that page open.

## Step 2 — Push this folder up with GitHub Desktop

1. Open GitHub Desktop → **File ▸ Add Local Repository**.
2. Choose this folder: `ais-hiring-snapshot`.
3. It will say "this directory does not appear to be a Git repository" →
   click **create a repository** → **Create Repository**.
4. Click **Publish repository** (top right). **Uncheck "Keep this code private."**
   Publish.

Your files are now on GitHub.

## Step 3 — Turn on the website

1. On GitHub, open your repo → **Settings ▸ Pages** (left sidebar).
2. Under **Build and deployment ▸ Source**, choose **GitHub Actions**.
   (That's it — nothing else to fill in.)

## Step 4 — Run it once

1. Go to the **Actions** tab of your repo.
2. If it asks, click to **enable workflows**.
3. Click **Snapshot & deploy** → **Run workflow** → **Run workflow**.
4. Wait ~1–2 minutes for the green check. Your site is now live at
   `https://<your-username>.github.io/ais-hiring-snapshot/`.

Link to that URL from your personal site and you're done.

---

## The weekly automation (already set up)

The workflow in `.github/workflows/snapshot-and-deploy.yml` runs **every Monday**,
pulls a fresh snapshot, commits it to `data/snapshots/`, rebuilds the site, and
redeploys. Over time those weekly snapshots accumulate into a history you can
later chart as a trend — the path to the "live tracker" version.

- **Change how often it runs:** edit the `cron:` line. `"17 9 * * 1"` means
  *Mondays at 09:17 UTC*. For example, daily would be `"17 9 * * *"`. (Helper:
  <https://crontab.guru>.)
- **Run it on demand any time:** Actions tab → Snapshot & deploy → Run workflow.
- **It won't loop:** the auto-commit is tagged `[skip ci]` so committing data
  doesn't trigger another run.

---

## Updating the site yourself

Anything you change locally (new orgs in `orgs.csv`, manual rows, copy edits):
in GitHub Desktop, write a short summary, click **Commit to main**, then **Push
origin**. The site rebuilds and redeploys on its own within a minute or two.

---

## Alternative: command line

```bash
cd ais-hiring-snapshot
git init && git add . && git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/ais-hiring-snapshot.git
git push -u origin main
```

Then do **Step 3** and **Step 4** above (Settings ▸ Pages ▸ Source: GitHub Actions,
then run the workflow).
