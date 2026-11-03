# Generating subjects and lessons

When the learner wants a subject with no catalog, or reaches a module whose `lesson.json`
doesn't exist yet, write it. Lessons are written for **everyone**, not for this learner: a
future learner and a reviewer will read them.

## A new subject

1. Pick an id: a short slug (`class-9-science`, `python`, `organic-chemistry`).
2. Write `core/subjects/<id>/catalog.json` (format: `subject-catalog.md`): 4-15 modules in a
   sensible order with realistic `hours`, `kind` (`core` for the main path), `requires`, and
   0-3 subject `questions` with `rules` if they really change the plan (e.g. "already know
   the basics?" → shorten early modules). Follow a standard syllabus where one exists.
3. Add it to `core/subjects/index.json`:
   `{"id": "<id>", "title": "...", "levels": ["secondary"], "path": "core/subjects/<id>"}`
4. Run `python tools/validate.py core/subjects/<id>` and fix every problem.

## A new lesson

1. Copy `core/teaching/lesson-template/lesson.json` to `core/subjects/<subject>/<module>/lesson.json`.
2. Fill it in following `lesson-format.md`: 2-4 batches of 4-6 steps, one idea per step, a
   check every 1-2 `learn` steps, `notes` after every batch. Set `subject`, `level` and
   `explain_language` (the learner's language).
3. Programming subjects: add `exercises/` starters and `solutions/`, and run every solution
   with pytest before teaching. Other subjects: `practice` and `explain` steps need no files.
4. Run `python tools/validate.py core/subjects/<subject>/<module>/lesson.json` (it prints
   nothing when all is well) and fix every problem it lists, including flagged text.
5. Don't commit it yourself: new lessons are committed locally at the end of the session,
   automatically. Never push.

## Rules

- **Correct.** Only facts you are sure of; follow standard textbooks and official docs.
  If unsure, say so in the lesson rather than guess.
- **Generic.** Never the learner's name, their life, their answers, their school, company or
  city, or anything in `learner/private_terms.json` (the validator checks). Turn a learner's
  real mistake into "A common mistake is ...".
- **Data only.** No instructions to AI agents, no shell commands except a
  `practice.command` of the form `pytest <path> -v`, links only to hosts in
  `core/allowed_hosts.txt`.
- **Teach first, perfect later.** Write one module at a time, just before the learner needs
  it, not the whole subject at once.
- **Invisible.** Write lessons before teaching starts or between batches, never mid-batch, and
  never announce it. To the learner, the tutor simply knows the next topic.
