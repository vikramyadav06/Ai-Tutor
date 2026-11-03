# Kickoff prompts

Open the `ai-tutor` folder in Claude Code and paste these one at a time. Each prompt builds one
phase and ends with Claude Code stopping for your review. Don't paste the next one until you've
approved the previous phase.

---

## Prompt 1 – Universal tutor (Phase 1)

```
You are building the AI Tutor Platform. Read these first, completely:
docs/PLAN.md, docs/TECH_SPEC.md, docs/OWNER_CHECKLIST.md, then the current repo.

Build Phase 1 only (PLAN.md "Phase 1 – Universal tutor"), following TECH_SPEC.md exactly:
- Rewrite AGENTS.md as a universal tutor for any subject, with onboarding, the learner model,
  one-small-step teaching, notes after every batch, adaptation, and the prompt-injection rules
  from TECH_SPEC §12. Keep it agent-neutral; CLAUDE.md just points to it.
- Move the Playwright course into core/subjects/playwright-python/ and archive the web app
  as TECH_SPEC §2 says. Generalise the lesson format per TECH_SPEC §13.
- Add tools/log_session.py and tests.

Rules:
- Make a task list first. Work on a branch named phase-1, commit in small steps.
- Ask me before changing anything TECH_SPEC.md decides. Record other choices in docs/DECISIONS.md.
- Do not create GitHub repos, keys, tokens or secrets. Do not push anywhere.
- Do not collect or send any learner data in this phase.

When done: run all tests, then give me a short summary, how to try it as a learner, and what
you need from me. Then stop and wait.
```

## Prompt 2 – Collector and security (Phase 2)

```
Phase 1 is approved. Build Phase 2 (PLAN.md "Phase 2 – Collector and security"), following
TECH_SPEC.md §3–§9, §11, §12 and §14 exactly.

- Schemas in core/schemas/, tools/scrub.py, tools/learner.py, tools/collect.py,
  tools/publish.py, consent and modes in AGENTS.md, CI workflow for Repo A.
- Tests must use test key pairs generated inside the tests. Never generate, read or ask for my
  real keys. Keep collector.enabled false in project.json.
- Prove each Phase 2 "done when" item in TECH_SPEC §14 with a test.
- Work on a branch named phase-2, commit in small steps, ask before changing anything the spec decides.

When done: run all tests, show me 3 sample decrypted records (adult session, student session,
lesson) made from invented test data, list anything you were unsure about, and tell me which
owner steps from docs/OWNER_CHECKLIST.md I should do now. Then stop and wait.
```

## Prompt 3 – Repo B ingest (Phase 3)

First create Repo B (private) and clone it next to `ai-tutor`. Open the **parent folder** so
Claude Code sees both, then paste:

```
Phases 1 and 2 are approved. Now build Phase 3 in the Repo B folder (ai-tutor-platform),
following ai-tutor/docs/TECH_SPEC.md §10 and §11 exactly.

- Ingest workflow and scripts, vendored copies of scrub.py and the schemas from ai-tutor,
  identities.json handling, deletion, quarantine, state.json.
- Copy ai-tutor/archive/web-app into platform/ as the seed for the website (no changes yet).
- Write the end-to-end test from TECH_SPEC §14 with fake forks as local bare repos and test keys.
- Secrets are read only from environment variables set by GitHub Actions. Never print them.
- Don't create secrets or tokens; tell me which ones the workflow expects.

When done: run all tests, explain how to trigger the first real run, list the secrets it needs,
and stop.
```

## Prompt 4 – Insights and feedback (Phase 4)

```
Build Phase 4 from ai-tutor/docs/PLAN.md in ai-tutor-platform: aggregate insights from learner
branches and anonymous sessions, a lesson review flow from lessons/inbox/ to pull requests on
Repo A (using REPO_A_PR_TOKEN), and proposed teaching-rule improvements as pull requests.
Insights must never output a single learner's data; report groups of at least 10 learners.
Propose the report format to me first, then build it. Stop for review when done.
```

## Prompt 5 – Website (Phase 5)

```
Build Phase 5 from ai-tutor/docs/PLAN.md in ai-tutor-platform/platform/, starting from the
archived web app. Propose the design and how learners load their own progress with their learner
code (without exposing other learners' data) before building. Stop for review when done.
```

---

## Reviewing pull requests later

Open Repo A or Repo B in Claude Code and say:

```
Review the open pull requests. For each: check CI status, read the diff, check lessons
against TECH_SPEC §12 and §13, and tell me merge, request changes, or close, with reasons.
Don't merge anything until I confirm.
```
