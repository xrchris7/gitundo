# 🚀 Publishing gitundo — step-by-step runbook

Everything below is copy-paste ready. Publishing takes **~20 minutes once** and
then CI can auto-publish every release forever after.

## What you need (3 free accounts)

| # | Account | Needed for | Create it at |
|---|---------|-----------|--------------|
| 1 | **GitHub** | hosting the repo + Actions | https://github.com/signup |
| 2 | **PyPI** | `pip install gitundo` | https://pypi.org/account/register/ |
| 3 | **VS Code Marketplace** (Microsoft/Azure) | the extension | https://marketplace.visualstudio.com/vscode |

---

## Step 0 — fill in your identity (30 seconds)

Two commands replace every `xrchris7` placeholder (README links, URLs, badges,
the website, the extension manifest, CI):

```bash
cd /home/user/gitundo
./scripts/set_owner.sh YOUR_GITHUB_USERNAME     # e.g. ./scripts/set_owner.sh alice
git add -A && git commit -m "chore: set owner metadata"
```

---

## Step 1 — Publish to GitHub

### 1a. Create the repository (paste these)

**Repository name:** `gitundo`

**Description** (paste into the "Description" box):

```
Automatic safety-net snapshots for any git repo — the undo button git never had. Never lose work to reset --hard, clean -fdx, a bad rebase or an accidental delete. Zero dependencies.
```

**Topics** (click "Add topics", paste one at a time, ≤ 20):

```
git, cli, developer-tools, checkpoint, snapshot, undo, git-tools, version-control, python, backup, recovery, developer-experience
```

Leave **Public**, **don't** tick "Add a README" (you have one).

### 1b. Push (replace `xrchris7`)

```bash
cd /home/user/gitundo
git init -b main
git add -A && git commit -m "gitundo 0.1.0 — CLI, guard, docs & VS Code extension"
git branch -M main
git remote add origin https://github.com/xrchris7/gitundo.git
git push -u origin main
```

### 1c. Polish on GitHub.com (2 minutes, makes it look loved)

1. Repo → **Settings → General → Social preview** → upload
   [`assets/social-preview.png`](assets/social-preview.png) (shows on link shares).
2. Repo → **About → ⚙** → add **Website** `https://xrchris7.github.io/gitundo`
   after Step 2.
3. Watch **Actions** run CI (3 jobs: 15-matrix Python tests, lint, VS Code build).

---

## Step 2 — Live website (the pretty one, 1 minute)

`docs/index.html` is the landing page (hero, animated terminal demo, features,
commands, install). It's fully self-contained and already in the repo.

1. Repo → **Settings → Pages**.
2. **Source:** *Deploy from a branch* → branch `main`, folder `/docs` → Save.
3. Wait ~60 s → your site is at `https://xrchris7.github.io/gitundo`.

> The `xrchris7` in the page's "GitHub" button was already replaced in Step 0.

---

## Step 3 — Publish to PyPI

The package metadata (name `gitundo`, version `0.1.0`, description, classifiers)
already lives in [`pyproject.toml`](pyproject.toml). You only need credentials:

```bash
cd /home/user/gitundo
python -m pip install build twine
python -m build                          # builds dist/*.whl + .tar.gz
# create an API token at https://pypi.org/manage/account/token/
#   scope: "entire account" (or a project-scoped token named "gitundo")
twine upload dist/*                      # paste username: __token__  password: pypi-xxxx
```

Then verify from anywhere:

```bash
pip install gitundo
gitundo --version
```

> If the name `gitundo` is somehow taken by the time you upload, pick a fallback
> (e.g. `gitundo-cli`) and change `name =` in `pyproject.toml`.

---

## Step 4 — Publish the VS Code extension

The extension manifest already carries the **name** (`gitundo`), **displayName**
(“gitundo — the undo button git never had”), short **description**, icon, and
keywords. `extensions/vscode/README.md` is used automatically as the Marketplace
long description.

```bash
# 1. Claim the publisher id (one-time, browser):
#    https://marketplace.visualstudio.com/manage  → "Create Publisher"
#    Publisher id:  gitundo      (or gitundo-dev if taken)
cd /home/user/gitundo/extensions/vscode
npm ci

# 2. One-time login with a Personal Access Token:
#    https://dev.azure.com/<you>  → User settings → Personal Access Tokens
#    Scope: Marketplace → Acquire & Manage
npx vsce login gitundo

# 3. Publish:
npm run package              # sanity: builds gitundo-0.1.0.vsix
vsce publish                 # publishes + bumps nothing (version from package.json)
```

If your publisher id differs from `gitundo`, also set `"publisher": "<id>"`
in `extensions/vscode/package.json` before publishing.

**Install your local build right now (no account needed):**

```bash
code --install-extension /home/user/gitundo/extensions/vscode/gitundo-0.1.0.vsix
```

---

## Step 5 — Make releases one command (recommended, ~5 minutes)

The repo already ships full publish workflows in `.github/workflows/ci.yml`.
Wire them up by adding **repo Secrets** (Settings → Secrets and variables →
Actions):

| Secret | Value |
|---|---|
| `PYPI_API_TOKEN` | your `pypi-…` token |
| `VSCODE_MARKETPLACE_TOKEN` | your Azure PAT |

Then releasing everything is literally one command:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

CI will: run tests → publish to PyPI → package + publish the extension →
(optionally) draft a GitHub Release.

> The PyPI job uses trusted/OpenID publishing by default; if you prefer tokens,
> set the `PYPI_API_TOKEN` secret and uncomment the env line in the workflow.

---

## What you now have (map of publishable files)

| File | Purpose | Pushed where |
|---|---|---|
| `README.md` | flagship description + docs | GitHub repo front page |
| `docs/index.html` | marketing landing page (self-contained) | GitHub Pages |
| `assets/social-preview.png` | link-share / repo preview image | GitHub social preview |
| `pyproject.toml` | PyPI name/description/version | PyPI (built) |
| `LICENSE`, `CHANGELOG.md`, `SECURITY.md` | trust signals | GitHub |
| `extensions/vscode/package.json` + `README.md` | Marketplace name/description/icon | Marketplace |
| `extensions/vscode/gitundo-0.1.0.vsix` | installable extension file | local / Marketplace |
| `.github/workflows/ci.yml` | tests + auto-publish on tags | GitHub Actions |

---

## Suggested first release notes (GitHub Release / v0.1.0)

```markdown
## 🛟 gitundo 0.1.0 — the undo button git never had

Automatic safety-net snapshots for any git repository. Snap your working
tree (staged + unstaged + untracked) any time, and restore it later — even
files you deleted. Never lose work to `reset --hard`, `clean -fdx`, a bad
rebase or an editor crash again.

- 📸 `gitundo snap` captures everything on disk (incl. untracked files)
- 🪂 `gitundo restore` brings any checkpoint back — history untouched
- 🛡️ auto-guard snapshots before destructive git commands
- 🏷️ tags, diffs, prune; selectors by number/tag/id
- 🧑‍💻 official VS Code extension (sidebar, one-click snap & restore)
- 🪶 zero dependencies, pure stdlib, Python 3.9+
- ✅ 75 tests against real git repos · MIT

pip install gitundo
```
