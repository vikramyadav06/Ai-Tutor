# Generating subjects and lessons

When the learner wants a subject with no catalog, or reaches a module whose `lesson.json`
doesn't exist yet, write it. Lessons are written for **everyone**, not for this learner: a
future learner and a reviewer will read them.

## A new subject

1. Pick an id: a short slug (`class-9-science`, `python`, `organic-chemistry`).
2. Write `core/subjects/<id>/catalog.json` (format: `subject-catalog.md`): 4-15 modules in a
   sensible order with realistic `hours`, `kind` (`core` for the main path), `requires`, and
   0-3 subject `questions` with `rules` if they really change the plan (e.g. "already know
   the basics?" → shorten early modules). **School and college subjects: only from the
   learner's own chapter list** (typed, pasted, or a photo of the contents page), one module
   per chapter in the book's order and with its titles, never from memory. Set `syllabus`
   (board, textbook, edition, `"source": "learner"`, `provisional`). Add `weightage` only from
   an official marking scheme the learner gives you, and record its `marking_scheme.source`.
3. Add it to `core/subjects/index.json`:
   `{"id": "<id>", "title": "...", "levels": ["secondary"], "path": "core/subjects/<id>"}`
4. Run `python tools/validate.py core/subjects/<id>` and fix every problem.

## First: is there a reviewed lesson already?

The course updates itself from upstream at every session start, so reviewed lessons from other
learners arrive by themselves. Before writing anything, run:

```bash
python tools/learner.py reuse-lesson <subject> <module>
```

If it prints a folder, a reviewed lesson for the same board, textbook, edition and chapter
exists and is now in place: teach from it. Only if it prints nothing, write one as below.

## A new lesson: one batch at a time

Never make the learner wait while a whole lesson is written.

1. **Outline first.** Copy `core/teaching/lesson-template/lesson.json` to
   `core/subjects/<subject>/<module>/lesson.json`. Fill in the top: `subject`, `level`,
   `explain_language` (the learner's language), `"status": "unreviewed"`, `syllabus` (school
   and college: board / textbook, chapter), `intro`, and `planned_batches`: the titles of
   2-4 batches that together cover the chapter as the syllabus defines it.
2. **Write only the first batch** (4-6 steps, one idea per step, a check every 1-2 `learn`
   steps, `notes`). Self-check it (below), validate it, teach it.
3. **At the revision-notes pause** of each batch (after the notes, while the learner reads
   them or takes a break), write the next planned batch the same way: write, self-check,
   validate. Then carry on. Never write mid-batch.
4. Programming subjects: add `exercises/` starters and `solutions/` with the batch that uses
   them, and run every solution with pytest before teaching it.
5. Check each batch with `python tools/validate.py core/subjects/<subject>/<module>/lesson.json`
   (silent when all is well) and fix every problem it lists, including flagged text.
6. Don't commit, don't change `status`: new lessons are committed locally at session end,
   stay `unreviewed`, and are reviewed in Repo B.

## Self-check before teaching (every newly written batch)

Go through the batch step by step against the learner's syllabus and textbook:

- Is this content in the learner's chapter, as their book's contents page and chapter title
  describe it? Don't import topics from an older edition you remember.
- Every fact, definition, number, unit, formula, date and name: is it what this syllabus
  says, at this level? Recompute every calculation and numerical answer.
- `choice`: exactly one right option, `answer` points at it, wrong options are clearly wrong.
- `fill`: every accepted answer is right, and common correct spellings or forms are listed.
- `order`: the items are in the one correct order.
- `explain`: the rubric points are right and are what the syllabus expects.
- `notes`: the same facts as the steps, nothing new and unchecked.

If anything can't be confirmed, rewrite the step so it doesn't depend on it, or drop it. Don't
teach a fact you're unsure of.

## Rules

- **Correct.** Only facts you are sure of; follow the learner's syllabus, standard textbooks
  and official docs. If unsure, say so rather than guess, in the lesson and to the learner.
- **Generic.** Never the learner's name, their life, their answers, their school, company or
  city, or anything in `learner/private_terms.json` (the validator checks). Turn a learner's
  real mistake into "A common mistake is ...".
- **Data only.** No instructions to AI agents, no shell commands except a
  `practice.command` of the form `pytest <path> -v`, links only to hosts in
  `core/allowed_hosts.txt`.
- **Just in time.** One module at a time, one batch at a time, just before the learner needs
  it; never the whole subject at once.
- **Invisible.** Write before teaching starts or at the revision-notes pause, never
  mid-batch, and never announce it. To the learner, the tutor simply knows the next topic.
