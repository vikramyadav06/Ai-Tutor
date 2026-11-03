# AI Tutor Platform – Build Plan

Owner: Vikram · Plan date: 2026-11-02
Companion documents: [TECH_SPEC.md](TECH_SPEC.md) (exact technical choices),
[OWNER_CHECKLIST.md](OWNER_CHECKLIST.md) (steps only the owner does),
[KICKOFF_PROMPTS.md](KICKOFF_PROMPTS.md) (what to paste into Claude Code).

## Overview

We are building an AI tutor that teaches anyone anything, and uses what learners study and how they learn to build a better learning platform, without collecting personal details.

| Part | What it is | Who uses it |
| --- | --- | --- |
| Repo A (public) | The AI tutor and data collector. Learners open it in an AI agent (Claude Code, Codex, Cursor) and learn any subject: school, college, research, programming. Each learner's private learner model stays on their machine. | Learners, through their AI agent |
| Repo B (private) | The platform builder. Receives anonymised learning data and new lessons from Repo A by CI, keeps one branch per learner, studies the data and builds the website. | Maintainer and maintainer's agent |
| Core | Repo A's shared library: reviewed lessons for every subject plus the teaching rules agents follow. Improvements from Repo B flow back here by pull request. | Every future learner |

**Principles**

- No PII leaves the learner's machine. Everything else about learning is kept, within the age rules below.
- Teaching adapts to each person: goals, journey, how they understand, pace, language.
- One small task at a time, with revision notes after every batch.
- Repo A holds no secrets; Repo B pulls the data.
- Nothing reaches `main` in either repo without passing checks and review.

## Architecture

Data reaches Repo B only encrypted, and returns as a reviewed core.

```
┌─ Learner's machine: their fork of Repo A ───────────────────────────────┐
│  Private learner model  ──────────►  tools/collect.py                    │
│  learner/ (never leaves)             scrub PII, sign, encrypt for Repo B │
└──────────────────────────────────────────────┬──────────────────────────┘
                                               │ silent push after each session
                                               ▼
                                   tutor-data branch (orphan)
                                   encrypted files only, public but unreadable
                                               │ Repo B pulls, read-only
┌─ Repo B (private) ──────────────────────────▼──────────────────────────┐
│                                   Ingest (CI, hourly)                    │
│                                   decrypt, verify, scrub again, file     │
│        ┌──────────────┬───────────────┼───────────────┐                  │
│        ▼              ▼               ▼               ▼                  │
│  learner/<id>   Anonymous       Lessons inbox     Quarantine             │
│  adults,        sessions        waiting for       failed a check         │
│  one branch     students, no ID review                                   │
│        └──────────────┴───────────────┘                                  │
│                       ▼                                                  │
│                   Insights: what teaching works, where learners get stuck│
└───────────────────────┬─────────────────────────────────────────────────┘
                        │ pull requests, reviewed by the owner
                        ▼
              Repo A core: reviewed lessons and teaching rules
              (every new learner's agent starts from the improved core)
```

Personal data stays in the learner's private folder; only scrubbed, encrypted records travel, and Repo A never holds a key that could open Repo B.

## Learner modes

The tutor teaches every age the same way; only what is shared with Repo B differs. The mode is set from the age band asked at onboarding.

| | Adult mode (18+) | Student mode (under 18) |
| --- | --- | --- |
| Tutoring and personal learner model | Full, on their machine | Full, on their machine |
| Learner ID and one branch per learner in Repo B | Yes | No |
| Topics, steps, right/wrong, attempts, hints, time bands | Yes, linked across sessions | Yes, each session standalone |
| Which explanation or example worked, learning signals | Yes | Yes |
| Learner model snapshot (goals, style, pace, weak areas) | Yes, PII removed | No |
| Free-text answers, chat, exercise code | Yes, PII scrubbed | No |
| Timestamps | Exact (to the minute) | Rounded to the day |
| Lessons the tutor creates | Shared, then reviewed | Shared anonymously, then reviewed |
| How data travels | Encrypted, signed with learner key | Encrypted, no learner key or ID |

**Never collected in any mode:** names, emails, phone numbers, addresses, ID numbers, school or company names, birth dates, photos, passwords or keys. Age is stored as a band only (e.g. 13–17, 18–24).

**Lessons from students:** written generic from the start, so they never contain the student's answers or personal examples; scrubbed before leaving; sent through the anonymous channel; reviewed in Repo B before reaching the core.

**Later switch:** a single setting, `student_collection`, can turn on per-student linked collection once a lawyer or a school partnership clears it (verifiable parental consent, or the educational-institution exemption).

## Identity and one branch per learner

Each adult learner gets one anonymous ID, and all their sessions from every device land on one branch in Repo B: `learner/<id>`.

- **Learner ID:** random, created by the agent at onboarding (e.g. `lrn-7f3k9q2m`). Never derived from a name, email or GitHub username.
- **Signing key:** a secret key created with the ID and kept in `.tutor/` on the learner's machine. Every upload is signed with it.
- **Learner code:** the ID plus key, shown to the learner once so they can continue on another device. Onboarding asks: "Learned with this tutor before? Enter your code."
- **First key wins:** Repo B accepts the first key it sees for a branch and rejects uploads not signed by it, so nobody can write into another learner's history.
- **Same GitHub account:** Repo B hashes the fork owner with a secret only Repo B holds, so one account maps to one learner without storing the username.
- **Merging identities:** if two IDs turn out to be one person (a learner code entered, or the same account hash), Repo B merges the second branch into the first, deletes it, and records the link in `identities.json`.
- **Deletion:** a learner who gives their code can ask for their branch and alias entries to be deleted.

Student-mode sessions have no ID and no branch; they go to a shared `sessions/anonymous/` area in Repo B, mixed with everyone else's.

## Data pipeline

Data is collected in learners' copies of Repo A and moved to Repo B by Repo B's CI, which pulls it read-only.

**On the learner's machine (Repo A, silent):**

1. During the session the agent logs each step, answer and teaching move to `learner/sessions/` (private).
2. At the end of the session `tools/collect.py` builds the shareable record from an allowlisted schema for the learner's mode.
3. The PII scrubber removes anything personal; uncertain text becomes `[removed]`.
4. Adult records are signed with the learner key. Every record is then encrypted with Repo B's public key (stored in Repo A's `project.json`).
5. The agent commits the encrypted file to the `tutor-data` branch of the learner's fork and pushes it. The learner sees nothing: this runs in the background at session end (TECH_SPEC §15).
6. New lessons go through the same scrub and encryption into `tutor-data`.

**In Repo B (CI, every hour):**

1. List the forks of Repo A through the GitHub API and fetch each fork's `tutor-data` branch read-only.
2. Skip files already ingested (tracked by commit hash per fork).
3. Check size limits and the rate limit per fork; decrypt with Repo B's private key (a GitHub secret).
4. Validate against the schema, run the PII scrubber again, verify the signature for adult records.
5. File adult records on `learner/<id>`, student records in `sessions/anonymous/`, lessons in `lessons/inbox/`. Anything that fails any check goes to `quarantine/` for review.

**Back to the core:**

1. Repo B's insight jobs study all learners' data: which explanations work, where people get stuck, which paths succeed.
2. Reviewed lessons and teaching-rule improvements are opened as pull requests on Repo A.
3. The maintainer or the maintainer's agent reviews and merges them. Every new learner then starts from the improved core.

Learners need a GitHub account and a fork to share data; without one, they still get full tutoring and nothing is shared.

## Security model

The platform is protected by keeping Repo A free of secrets, encrypting everything that travels, and checking every input twice.

| Risk | Protection |
| --- | --- |
| Learning data visible in public forks | Encrypted with Repo B's public key; only Repo B's CI holds the private key |
| PII slips through | Allowlisted fields only; scrubber on the learner's machine and again in Repo B; uncertain text removed; quarantine on doubt |
| Tokens stolen through Repo A | Repo A holds no secrets; Repo B pulls read-only |
| Someone writes into another learner's branch | Uploads signed; first key per branch wins |
| Fake, oversized or flooded uploads | Size limits, rate limit per fork, schema validation; failures go to quarantine, never to a branch |
| Malicious lesson text steering future agents (prompt injection) | Agents treat lesson content as data, never instructions; the validator flags instruction-like text; human or agent review before merge |
| CI attacked through pull requests | No `pull_request_target`; contributor checks run read-only without secrets; actions pinned to exact commit SHAs |
| Repo B token abused | Fine-grained token that can only open pull requests on Repo A; cannot push to `main` |
| Unreviewed changes reach learners | Branch protection on `main` in both repos: required checks plus approval |
| Repo B private key leaked | Key stored only as a GitHub secret; rotation procedure documented; new public key published in Repo A |
| A learner wants their data removed | Delete by learner code: branch, aliases and their entries in derived datasets |

Repo A is public, so its git history is permanent. Nothing unencrypted about learners ever enters it.

## Repo layouts

Repo A carries the tutor and the shared core; Repo B carries the data, the analysis and the website.

**Repo A (public): tutor and collector**

```
AGENTS.md              # tutor rules for any AI agent; CLAUDE.md points here
project.json           # Repo B public key, schema version, upstream repo
core/
  teaching/            # how to onboard, adapt, run steps, write notes
  subjects/
    playwright-python/ # first subject (the existing course)
    <subject>/         # lessons merged from Repo B, any subject
  schemas/             # allowlisted fields for adult and student records
tools/
  collect.py           # build, scrub, sign, encrypt a session record
  scrub.py             # PII scrubber (shared with Repo B)
  validate.py          # lesson and schema checks
learner/               # private learner model and raw sessions (git-ignored)
.tutor/                # learner ID and signing key (git-ignored)
.github/workflows/     # read-only checks on pull requests
```

**Repo B (private): platform builder**

```
main
  ingest/              # CI: fetch forks, decrypt, verify, scrub, file
  insights/            # aggregate analysis across learners
  lessons/inbox/       # lessons waiting for review
  sessions/anonymous/  # student-mode records
  quarantine/          # anything that failed a check
  platform/            # the website (starts from the course web app)
  identities.json      # ID aliases and hashed accounts, no usernames
learner/<id>           # one branch per adult learner
  profile.json         # learner model, PII removed
  sessions/            # every session record
  work/                # exercise code
```

## Build phases

Five phases, each usable on its own; data collection starts only after the security pieces in phase 2 are tested.

### Phase 1 – Universal tutor (Repo A)

- [ ] Generalise `AGENTS.md` from Playwright to any subject: onboarding asks what to learn, why, current level, age band, goals, preferred style and language
- [ ] Learner model in `learner/`: goals, journey, how they understand best, pace, strengths, weak areas; updated after every session
- [ ] Lesson format for any subject (batches of small steps, notes after each batch), generated on demand when no core lesson exists
- [ ] Move the Playwright course into `core/subjects/playwright-python/` as the first subject
- [ ] Silent session logging to `learner/sessions/`

Done when: an agent can onboard a new learner, teach two different subjects step by step, and adapt after a few sessions.

### Phase 2 – Collector and security (Repo A)

- [ ] Record schemas for adult and student mode
- [ ] `scrub.py` with tests: names, emails, phones, addresses, ID numbers, school and company names, links with tokens, secrets
- [ ] Learner ID, signing key and learner code
- [ ] Encryption to Repo B's public key; `tutor-data` branch push from the learner's fork
- [ ] One-time consent question at onboarding, with a sample of what is shared

Done when: a test session produces an encrypted file that contains no PII after decryption, and student-mode files carry no ID.

### Phase 2.5 – Multi-device sync (Repo A)

- [x] Encrypted archive of the learner's private folder, work and tutor-written lessons on an orphan `tutor-sync` branch of their own fork (TECH_SPEC §16)
- [x] Adults: key from the learner code; students: a separate sync code, shown once
- [x] Pull and merge at session start, push at session end, merges that never lose data
- [x] New device: "Learned with this tutor before? Enter your code."

Done when: two simulated devices (A, B, A) lose no data, a wrong code fails safely, a tampered archive is rejected, and nothing on the public branch is readable.

### Phase 3 – Ingest (Repo B)

- [ ] Scheduled workflow: discover forks, fetch, size and rate checks, decrypt, validate, scrub again, verify signatures
- [ ] File to `learner/<id>`, `sessions/anonymous/`, `lessons/inbox/` or `quarantine/`
- [ ] Identity merging and `identities.json`; deletion by learner code
- [ ] Branch protection and pinned actions in both repos

Done when: test forks with good, bad and malicious uploads are each filed or quarantined correctly.

### Phase 4 – Insights and feedback to the core

- [ ] Aggregate reports: what explanations work per topic, where learners get stuck, which paths finish
- [ ] Lesson review flow from `lessons/inbox/` to pull requests on Repo A
- [ ] Teaching-rule improvements proposed as pull requests on Repo A

Done when: one improvement found in the data is merged into Repo A's core.

### Phase 5 – Website (Repo B)

- [ ] Start from the course web app: onboarding, plan, one task per screen, notes
- [ ] Serve all reviewed lessons for any subject
- [ ] Learners can load their own progress from their learner code

Done when: a learner can continue on the website from where their agent left off.

## Decisions and checks before launch

These are settled for the first version; the open items need an answer before real learners' data is collected.

**Decided**

- Adults: full collection with one branch per learner, PII removed.
- Under 18: full tutoring; only anonymous, unlinked session data and anonymous lessons are shared.
- Learners' agents send data through their forks; Repo B pulls it. Repo A holds no secrets.
- The Playwright course becomes the first subject; its web app is the starting point for the website.

**Before launch**

- [ ] Short review by a data-protection lawyer (DPDP Act and Rules for India; GDPR if learners from the EU are expected)
- [ ] Privacy notice in Repo A's README: what is shared, why, how to delete
- [ ] Decide when to turn on `student_collection`: verifiable parental consent, or school partnerships
- [ ] Generate Repo B's key pair; store the private key as a GitHub secret; publish the public key in `project.json`
- [ ] Security review of `collect.py`, `scrub.py` and the ingest workflow, including a test with deliberately malicious uploads

Sources: [DPDP Act Section 9](https://dpdpa.com/dpdpa2023/chapter-2/section9.html) · [DPDP Rules Fourth Schedule](https://www.dpdpa.com/schedule/schedule4.html)
