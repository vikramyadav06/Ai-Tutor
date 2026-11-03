# AI Tutor

A personal tutor that teaches anyone anything: school subjects, college, research,
programming. Open this folder in an AI agent (Claude Code, Codex, Cursor) and say **start**.

The tutor asks a few questions (what you want to learn and why, your level, how you like to
learn, your language), builds a plan, and then teaches **one small step at a time**: one
idea, a quick check, feedback, the next step. After every short batch you get **revision
notes**, saved for later. It adapts as it goes: slower where you struggle, faster where you
don't, using the kinds of explanation that work for you.

Everything it learns about you stays in `learner/` on your computer. Nothing is shared.

## Start

```bash
git clone <this-repo-url>
cd <repo-folder>
```

Open the folder in your AI agent and say **start**. You need Python 3.10 or newer.
If you agree to share anonymous learning data, the tutor asks to install two small packages
(pinned, hash-checked) into `.tutor/pylib` in this folder. Teaching works without them.

Some subjects have hands-on exercises with their own packages. The tutor tells you when; for
example, the Playwright subject needs:

```bash
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
pip install -r core/subjects/playwright-python/requirements.txt
playwright install --with-deps
```

## Subjects

Any subject works: if there is no lesson yet, the tutor writes one. Reviewed subjects:

| Subject | Folder |
| --- | --- |
| Playwright with Python (web test automation) | [`core/subjects/playwright-python`](core/subjects/playwright-python) |

## Repository layout

```
├── AGENTS.md            # tutor rules for any AI agent (CLAUDE.md points here)
├── .claude/settings.json  # Claude Code: background hooks, no permission prompts for bookkeeping
├── core/
│   ├── teaching/        # onboarding, learner model, steps and notes, adaptation, lesson format
│   ├── subjects/        # index.json + one folder per subject (catalog.json, <module>/lesson.json)
│   ├── schemas/         # what may be shared: adult, student, lesson and delete records
│   └── allowed_hosts.txt
├── tools/
│   ├── tutor.py         # all background work: one quiet call per batch, session hooks
│   ├── learner.py       # profile, learner model, plans, notes (all private, in learner/)
│   ├── log_session.py   # session log in learner/sessions/
│   ├── tutorlog.py      # quiet failure log and retry queue
│   ├── scrub.py         # removes personal details before anything is shared
│   ├── collect.py       # builds, scrubs, signs and encrypts shareable records
│   ├── publish.py       # pushes encrypted records to your fork's tutor-data branch
│   ├── guard.py         # Claude Code hook: chained tutor commands always ask first
│   ├── validate.py      # checks subjects and lessons, flags prompt-injection text
│   └── owner/           # owner-only scripts
├── tests/               # pytest tests for the tools
├── my-work/             # your exercise code
├── learner/             # your profile, plans, notes, sessions (private, git-ignored)
├── archive/web-app/     # the old browser version, kept as the seed for the website
├── project.json         # public settings (data collection is off)
└── docs/                # plan and technical spec for building the platform
```

## For developers

```bash
pip install --require-hashes --no-deps -r requirements-tutor.txt
pip install -r requirements-dev.txt
pytest
python tools/validate.py
```

The build plan is in [docs/PLAN.md](docs/PLAN.md) and the exact choices in
[docs/TECH_SPEC.md](docs/TECH_SPEC.md). Decisions not covered there: [docs/DECISIONS.md](docs/DECISIONS.md).
