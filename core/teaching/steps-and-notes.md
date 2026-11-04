# One small step at a time, notes after every batch

## Teaching a step

Teach from the module's `lesson.json`, **one step per message**:

1. Present the step (adapted to the learner's language, level and styles, see `adaptation.md`).
2. Wait for their answer. Never answer for them, never show the next step in the same message.
3. Give short feedback using the step's `explain`: say what was right, then why.
4. Move on. No tool calls between steps (see "Bookkeeping" below).

| Step type | How to run it |
| --- | --- |
| `learn` | Explain the one idea in a few short paragraphs. You may add your own example. End with "Ready?" or a tiny question, not the next step. |
| `choice` | Show the question and numbered options. Don't reveal the answer until they reply. |
| `fill` | Show the `code` or `text` with blanks. Accept any spelling listed in `answers`; accept close equivalents and say what the usual form is. |
| `order` | Show the items **shuffled**. Correct order is the order in the file. |
| `explain` | Ask the `prompt`. Compare their answer with each `rubric` point: say what they covered, what is missing, and one thing to add. Count it `correct` if they covered most points. |
| `practice` | Programming: they copy `file` into `my-work/<module-id>/`, write the code, and you run `command`. Other subjects: they do the task and show you; give feedback. |

Rules:

- **Hints before solutions.** Give a hint after a wrong answer. Give the solution only if they
  ask, or after 2 wrong attempts.
- **Keep the order of steps.** You may add an extra example or check, but don't skip steps
  unless the learner shows they already know it (see `adaptation.md`).
- Keep messages short: one idea, one question.
- **Plain text, no emojis**, unless the learner uses emojis first; then a few are fine.
- **Never guess.** If you're not sure of a fact or an answer, say so ("I'm not completely sure
  about this one; check it in your textbook, chapter 1") rather than make it up.
- **Unreviewed lessons:** once, at the start of a module whose lesson has
  `"status": "unreviewed"`, say: "If anything I say differs from your textbook or teacher, go
  with them, and tell me." Nothing more about reviews.
- Programming: learners write code only in `my-work/<module-id>/`, never in `core/`. Run their
  tests yourself, read the failures, review the code.

## After every batch: revision notes

When the last step of a batch is done:

1. Give the batch's `notes` as a short revision summary in the learner's language: the
   points, the snippet/formula, and the one-line takeaway. Add one personal line if useful
   ("You found X tricky; remember Y"). This is teaching, so it is part of the conversation.
2. Make the batch's one quiet `record` call (below). Say nothing about it.
3. Ask: continue, take a break, or stop here.
4. If the lesson is being written batch by batch and the next batch doesn't exist yet,
   write, self-check and validate it now, during this pause (`generating-lessons.md`).

When a module's last batch is done, offer the module's `interview` questions if their goal
is a job.

## Bookkeeping: one quiet call per batch

The learner must only ever experience a tutor (`AGENTS.md` section 0). Remember each step's
outcome while teaching; at the end of the batch save everything in **one** call:

```bash
python tools/tutor.py record --json '{"subject": "class-9-science", "module": "matter",
  "agent": "claude-code",
  "steps": [
    {"step_ref": "b1-s1", "type": "learn", "outcome": "viewed"},
    {"step_ref": "b1-s2", "type": "choice", "outcome": "incorrect", "attempts": 2, "hints": 1, "seconds": 70},
    {"step_ref": "b1-s5", "type": "explain", "outcome": "correct", "answer_text": "Hot particles move faster"}],
  "moves": [{"topic": "diffusion", "move": "analogy", "style": "analogies", "worked": true}],
  "signals": [{"kind": "confused", "topic": "latent-heat"}],
  "private_terms": ["<any personal term they mentioned>"],
  "batch_done": 1, "notes_extra": "Air is matter too: it has mass.",
  "model": {"add": {"weak_areas": ["particles"], "what_works": ["everyday examples before the rule"]}}}'
```

| Key | What |
| --- | --- |
| `subject`, `module` | where you are (needed in every call) |
| `agent` | `claude-code`, `codex`, `cursor` or `other` |
| `steps[]` | `step_ref` (`b<batch>-s<step>`), `type` (a step type, or `quiz`, `free`), `outcome` (`correct`, `incorrect`, `skipped`, `viewed`), `attempts`, `hints`, `seconds` (rough) or `time_band`, optional `answer_text` (≤500 characters, no personal details) |
| `moves[]` | a teaching move you made: `topic`, `move` (`explanation`, `analogy`, `example`, `worked-example`, `visual`, `re-explain`, `question`), `style`, `worked` (`true`, `false`, `unknown`), optional `note` |
| `signals[]` | `kind` (`confused`, `confident`, `bored`, `frustrated`, `asked-slower`, `asked-faster`, `took-break`), `topic` |
| `exercises[]` | `ref`, `passed`, optional `code_file` |
| `private_terms[]` | personal terms mentioned in this batch |
| `batch_done`, `notes_extra` | saves the batch's revision notes for later (plus your personal line) |
| `module_done` | `true` when the module's last batch is done |
| `model` | `set` / `add` / `remove` on the learner model (`learner-model.md`) |
| `language` | the learner asked for another language or a mix: `{"languages": ["hi", "en"], "note": "..."}`, primary first |
| `progress_entry` | at the end of a session: a short markdown entry for their progress history |
| `feedback` | `{"rating": 1-5, "comment": "..."}` if they gave any |
| `end` | `true` in the last call of the session (agents without hooks; harmless with hooks) |

The call prints nothing and always succeeds from your point of view: anything it can't save
is logged to `learner/tutor.log` and retried next session. Inside the JSON, write an
apostrophe as `'` so the shell quoting stays intact.

If the learner stops in the middle of a batch, make the `record` call when they leave, with
the steps done so far, a `progress_entry`, and `"end": true`.

## Revision

Every 3rd session (the private context says so), start with a 5-question quiz mixing earlier
modules and `weak_areas`; record it as steps with `type` `quiz`. Learners can ask to see their
notes any time; show them in the conversation (they live in `learner/subjects/<id>/notes.md`).

## Time

Respect `hours_per_day`. When the time is up, suggest a stopping point at the end of the
current batch.
