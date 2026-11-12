# Owner checklist

Steps only you (the owner) do. Claude Code must not do these for you: they involve your
accounts, keys and legal decisions. Tick them as you go.

## Before Phase 1 (10 minutes)

- [ ] Create **Repo A** on GitHub, public, `vikramyadav06/Ai-Tutor`. Push this `ai-tutor` folder to it:
      ```
      cd ai-tutor
      git init -b main && git add -A && git commit -m "Starting point"
      git remote add origin https://github.com/vikramyadav06/Ai-Tutor.git
      git push -u origin main
      ```
- [ ] Install the GitHub CLI and sign in: `gh auth login`
- [x] Replace the `OWNER/...` placeholders with `vikramyadav06/Ai-Tutor` and `vikramyadav06/Ai-Tutor-Platform` in `project.json`,
      `docs/TECH_SPEC.md` and `tools/owner/generate_keys.py` with your real repo names
      (Claude Code can do this find-and-replace if you tell it the names)
- [ ] Open the folder in Claude Code and paste **Prompt 1** from `KICKOFF_PROMPTS.md`

## After Phase 1 (review)

- [ ] Try it as a learner yourself: start a fresh Claude Code session in a copy of the repo,
      onboard, learn two different subjects for 15 minutes each
- [ ] Approve or ask for changes, then paste **Prompt 2**

## During or after Phase 2: keys and Repo B

- [x] Create **Repo B** on GitHub, **private**, `vikramyadav06/Ai-Tutor-Platform`
- [ ] Generate the collector keys **yourself, in your own terminal** (not through Claude Code):
      ```
      pip install pynacl==1.5.0
      python tools/owner/generate_keys.py k1
      ```
- [ ] Store the two secrets in Repo B, then delete the files:
      ```
      gh secret set COLLECTOR_PRIVATE_KEY_K1 --repo vikramyadav06/Ai-Tutor-Platform < collector_private_k1.txt
      gh secret set ACCOUNT_HASH_KEY        --repo vikramyadav06/Ai-Tutor-Platform < account_hash_key.txt
      rm collector_private_k1.txt account_hash_key.txt
      ```
- [x] Put the printed **public** key into `project.json` → `collector.keys[0].public_key_b64`
      (public keys are safe to share; tell Claude Code the value or edit it yourself)
- [ ] Keep an offline backup of the private key (password manager). If it's lost, old data
      can't be read; if it leaks, follow "Key rotation" below.

## Phase 3: connect Repo B and run the ingest

Claude Code built Repo B in `/home/webgarh/Projects/Ai-Tutor-Platform` (it can't reach GitHub
from here). In your own terminal:

- [ ] Push it to the empty private repo (if GitHub made a README there, delete the repo's
      content first or tell Claude Code):
      ```
      cd ~/Projects/Ai-Tutor-Platform
      git remote add origin https://github.com/vikramyadav06/Ai-Tutor-Platform.git
      git push -u origin main
      ```
- [ ] Repo B → Settings → Secrets and variables → Actions: `COLLECTOR_PRIVATE_KEY_K1` and
      `ACCOUNT_HASH_KEY` (above). `GITHUB_TOKEN` is automatic.
- [ ] Repo B → Settings → Actions → General: allow GitHub Actions to run.
- [ ] First run: Actions → **Ingest** → Run workflow. With no shared data yet it commits only
      `ingest/state.json` and `ingest/identities.json`; the log shows counts only.
- [ ] Test before real learners: on a throwaway GitHub account, fork Repo A, set
      `collector.enabled` to `true` **in that fork only**, do a short session, then run Ingest and
      check the record appears (adult: a `learner/lrn-…` branch; student: `sessions/anonymous/`).

## Protect both repos (GitHub → Settings)

- [ ] **Repo B `main`**: the hourly ingest commits to `main` and to `learner/*` branches with
      the workflow's own token, so it can't go through pull requests. Add a ruleset for `main` that
      **blocks force pushes and deletions only**; leave `learner/*` unprotected (ingest deletes
      those branches when a learner asks). Repo B is private and only you can push to it.
      On a free personal account GitHub saves but **does not enforce** rulesets on private
      repos (it needs GitHub Pro or a Team organization). Create it anyway; until then the
      protection is that only you have write access, the ingest only fast-forwards `main`, and
      Actions may run only GitHub-made actions pinned to a commit SHA.
- [ ] **Branches → Add branch ruleset for `main`** (Repo A; and Repo B's code through pull
      requests by habit): require a pull request,
      require 1 approval, **require review from Code Owners** (`.github/CODEOWNERS` makes you the
      owner of `tools/`, `.claude/`, `AGENTS.md`, `CLAUDE.md`, `project.json`,
      `requirements-*.txt`, `core/schemas/`, `docs/allowed_signers` and `.github/`), require
      status checks to pass, block force pushes, block deletions.
      GitHub never lets an author approve their own pull request, so as the only code owner
      either add yourself to the ruleset's **bypass list, for pull requests only** (never "always"),
      or have a second trusted maintainer review your changes.
- [x] **Tags → Add tag ruleset for `v*`** (Repo A): **restrict updates and deletions** and
      **block force pushes**, so a published release can never be moved or removed. Don't
      restrict creations: on a personal account GitHub rejected the owner's own tag push even
      with "Repository admin: Always allow" in the bypass list. Only you have write access, so
      only you can create tags anyway, and learners accept only tags signed by
      `docs/allowed_signers`.
- [ ] **Actions → General**: "Read repository contents permission" as the default;
      "Require approval for all outside collaborators" for fork pull requests (Repo A)
- [ ] **Code security**: turn on Dependabot alerts and Dependabot version updates for Actions
- [ ] **Secret scanning and push protection**: on (both repos)

## Your GitHub account

- [ ] **Two-factor authentication with a passkey or a hardware security key** (GitHub →
      Settings → Password and authentication). Remove SMS as a fallback. Store the recovery
      codes offline. Whoever controls this account controls what runs on every learner's machine.

## Releases and signing (learners update only to signed releases, TECH_SPEC §17)

One-time setup, **yourself, in your own terminal** (not through an AI agent):

- [x] Create an SSH key used **only** for signing releases, with a passphrase:
      ```
      ssh-keygen -t ed25519 -C "ai-tutor releases" -f ~/.ssh/ai_tutor_release
      ```
      Keep an offline backup of the private key file (password manager). Never use it for
      logging in to servers or GitHub.
- [ ] Tell git to sign with it, in your Repo A checkout only:
      ```
      git config gpg.format ssh
      git config user.signingkey ~/.ssh/ai_tutor_release.pub
      git config gpg.ssh.allowedSignersFile docs/allowed_signers
      ```
      (the last line lets `git verify-tag` check your tags against the trusted keys)
- [ ] Add the **public** key to `docs/allowed_signers` by pull request (one line):
      ```
      echo "vikram-release namespaces=\"git\" $(cut -d' ' -f1,2 ~/.ssh/ai_tutor_release.pub)" >> docs/allowed_signers
      ```
      Until this line is merged and a learner's copy has it, learners receive no updates.
      Copies cloned **before** it was merged have no trusted key, so they never update by
      themselves: those learners (and your own test copy) need a fresh clone once.
- [ ] Optional: add the same public key to GitHub as a **signing key** (Settings → SSH and GPG
      keys → New SSH key → type "Signing key"), so GitHub shows releases as Verified.

To cut a release (after the reviewed pull requests are merged to `main` and checks are green):

```
git switch main && git pull --ff-only
git log --oneline -5                       # check this is exactly what you want to ship
git tag -s v2026.11.03 -m "Release v2026.11.03"   # second release that day: v2026.11.03.1
git verify-tag v2026.11.03                 # must say: Good "git" signature for vikram-release
git push origin v2026.11.03
```

Learners' tutors pick it up at their next session start. Notes:

- **Changing collector keys** (`project.json`): learners send nothing until the same keys
  appear in **two consecutive signed releases**. Release the key change, then cut a second
  release (it can be a small one) before you expect data with the new key.
- **Rotating the release key:** add the new public key to `docs/allowed_signers` and release
  that change signed with the **old** key; sign later releases with the new key; then remove
  the old line in a release signed with the new key.
- **If the release key may have leaked:** stop releasing, remove its line from
  `docs/allowed_signers` in a release signed by another trusted key, and review recent tags.
  (Learners who never received that release still trust the old key until they do.)

## Before Phase 4: token for Repo B → Repo A pull requests

- [ ] GitHub → Settings → Developer settings → **Fine-grained tokens → Generate**:
      Repository access: only Repo A. Permissions: **Contents: Read and write**,
      **Pull requests: Read and write**, nothing else. Expiry: 90 days.
- [ ] Store it in Repo B: `gh secret set REPO_A_PR_TOKEN --repo vikramyadav06/Ai-Tutor-Platform`
- [ ] Calendar reminder to renew it before it expires

## Before switching on collection (`collector.enabled: true`)

- [ ] Phase 2 and Phase 3 tests all green, including the malicious-upload test
- [ ] Read 10 decrypted test records yourself and confirm nothing personal is in them
- [ ] Data-protection lawyer reviewed the plan, the privacy notice and the student mode
- [ ] Privacy notice added to Repo A's README (Claude Code drafts it; you approve it)
- [ ] Then, and only then, set `collector.enabled` to `true` in `project.json`

## Key rotation (if the private key may have leaked)

1. Run `python tools/owner/generate_keys.py k2`, store `COLLECTOR_PRIVATE_KEY_K2` in Repo B.
2. In `project.json`, add `k2` as `active` and mark `k1` as `retired`. Merge to Repo A.
3. Keep `COLLECTOR_PRIVATE_KEY_K1` until all `k1` files are ingested, then delete that secret.
4. Review Repo B's access log and recent commits for anything unexpected.

## Never

- Never paste a private key, token or secret into Claude Code or any chat.
- Never make Repo B public.
- Never merge to `main` with red checks.
- Never sign a release tag on a commit you haven't reviewed, and never let an agent sign one.
