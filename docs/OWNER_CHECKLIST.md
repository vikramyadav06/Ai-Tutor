# Owner checklist

Steps only you (the owner) do. Claude Code must not do these for you: they involve your
accounts, keys and legal decisions. Tick them as you go.

## Before Phase 1 (10 minutes)

- [ ] Create **Repo A** on GitHub, public, `vikramwebgarh/Ai-Tutor`. Push this `ai-tutor` folder to it:
      ```
      cd ai-tutor
      git init -b main && git add -A && git commit -m "Starting point"
      git remote add origin https://github.com/vikramwebgarh/Ai-Tutor.git
      git push -u origin main
      ```
- [ ] Install the GitHub CLI and sign in: `gh auth login`
- [x] Replace the `OWNER/...` placeholders with `vikramwebgarh/Ai-Tutor` and `vikramwebgarh/Ai-Tutor-Platform` in `project.json`,
      `docs/TECH_SPEC.md` and `tools/owner/generate_keys.py` with your real repo names
      (Claude Code can do this find-and-replace if you tell it the names)
- [ ] Open the folder in Claude Code and paste **Prompt 1** from `KICKOFF_PROMPTS.md`

## After Phase 1 (review)

- [ ] Try it as a learner yourself: start a fresh Claude Code session in a copy of the repo,
      onboard, learn two different subjects for 15 minutes each
- [ ] Approve or ask for changes, then paste **Prompt 2**

## During or after Phase 2: keys and Repo B

- [ ] Create **Repo B** on GitHub, **private**, `vikramwebgarh/Ai-Tutor-Platform`
- [ ] Generate the collector keys **yourself, in your own terminal** (not through Claude Code):
      ```
      pip install pynacl==1.5.0
      python tools/owner/generate_keys.py k1
      ```
- [ ] Store the two secrets in Repo B, then delete the files:
      ```
      gh secret set COLLECTOR_PRIVATE_KEY_K1 --repo vikramwebgarh/Ai-Tutor-Platform < collector_private_k1.txt
      gh secret set ACCOUNT_HASH_KEY        --repo vikramwebgarh/Ai-Tutor-Platform < account_hash_key.txt
      rm collector_private_k1.txt account_hash_key.txt
      ```
- [ ] Put the printed **public** key into `project.json` → `collector.keys[0].public_key_b64`
      (public keys are safe to share; tell Claude Code the value or edit it yourself)
- [ ] Keep an offline backup of the private key (password manager). If it's lost, old data
      can't be read; if it leaks, follow "Key rotation" below.

## Protect both repos (GitHub → Settings)

- [ ] **Branches → Add branch ruleset for `main`** (both repos): require a pull request,
      require 1 approval, require status checks to pass, block force pushes, block deletions
- [ ] **Actions → General**: "Read repository contents permission" as the default;
      "Require approval for all outside collaborators" for fork pull requests (Repo A)
- [ ] **Code security**: turn on Dependabot alerts and Dependabot version updates for Actions
- [ ] **Secret scanning and push protection**: on (both repos)

## Before Phase 4: token for Repo B → Repo A pull requests

- [ ] GitHub → Settings → Developer settings → **Fine-grained tokens → Generate**:
      Repository access: only Repo A. Permissions: **Contents: Read and write**,
      **Pull requests: Read and write**, nothing else. Expiry: 90 days.
- [ ] Store it in Repo B: `gh secret set REPO_A_PR_TOKEN --repo vikramwebgarh/Ai-Tutor-Platform`
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
