# One small step at a time, notes after every batch

## Teaching a step

Teach from the module's `lesson.json`, **one step per message**:

1. Present the step (adapted to the learner's language, level and styles, see `adaptation.md`).
2. Wait for their answer. Never answer for them, never show the next step in the same message.
3. Give short feedback using the step's `explain`: say what was right, then why.
4. Log it silently and move on.

| Step type | How to run it |
| --- | --- |
| `learn` | Explain the one idea in a few short paragraphs. You may add your own example. End with "Ready?" or a tiny question, not the next step. |
| `choice` | Show the question and numbered options. Don't reveal the answer until they reply. |
| `fill` | Show the `code` or `text` with blanks. Accept any spelling listed in `answers`; accept close equivalents and say what the usual form is. |
| `order` | Show the items **shuffled**. Correct order is the order in the file. |
| `explain` | Ask the `prompt`. Compare their answer with each `rubric` point: say what they covered, what is missing, and one thing to add. Mark `correct` if they covered most points. |
| `practice` | Programming: they copy `file` into `my-work/<module-id>/`, write the code, and you run `command`. Other subjects: they do the task and show you; give feedback. |

Rules:

- **Hints before solutions.** Give a hint after a wrong answer. Give the solution only if they
  ask, or after 2 wrong attempts.
- **Keep the order of steps.** You may add an extra example or check, but don't skip steps
  unless the learner shows they already know it (see `adaptation.md`).
- Keep messages short: one idea, one question.
- Programming: learners write code only in `my-work/<module-id>/`, never in `core/`. Run their
  tests yourself, read the failures, review the code.

## Logging (silent)

At the start of a session, and after every step:

```bash
python tools/log_session.py start --subject <id> --module <id> --agent <claude-code|codex|cursor|other>
python tools/log_session.py step --module <id> --step-ref b1-s3 --type choice \
    --outcome correct --attempts 1 --hints 0 --seconds 40
```

`step-ref` is `b<batch>-s<step>`. When you used a teaching move (an analogy, a worked example,
a re-explanation) log it and whether it worked:

```bash
python tools/log_session.py move --topic <slug> --move analogy --style analogies --worked true
python tools/log_session.py signal --kind confused --topic <slug>
```

`--answer-text` and `--note` are optional; never put personal details in them. At the end:
`python tools/log_session.py end`. Never show the log to the learner unless they ask.

## After every batch: revision notes

When the last step of a batch is done:

1. Give the batch's `notes` as a short revision summary in the learner's language: the
   points, the snippet/formula, and the one-line takeaway. Add one personal line if useful
   ("You found X tricky; remember Y").
2. Save them: `python tools/learner.py notes <subject> <module> <batch number> --extra "<that personal line>"`
3. Log it: `python tools/log_session.py batch --module <id> --batch <n>`
4. Ask: continue, take a break, or stop here.

When a module's last batch is done: `python tools/learner.py progress <subject> <module> done`,
update the learner model, and offer the module's `interview` questions if their goal is a job.

## Revision

Every 3rd session, start with a 5-question quiz mixing earlier modules and `weak_areas`
(log each as `--type quiz`). Learners can ask to see their notes any time:
`learner/subjects/<id>/notes.md`.

## Time

Respect `hours_per_day`. When the time is up, suggest a stopping point at the end of the
current batch.
