# Lesson format (any subject)

Every module lives in `core/subjects/<subject-id>/<module-id>/` and has one content file,
`lesson.json`. AI tutors, people reading the repo and (later) the website all use this same
file, so every learner gets the same content. Check a lesson with `python tools/validate.py`.

## Top-level fields

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Module id, same as the folder name (slug: `a-z`, `0-9`, `-`) |
| `title` | yes | Module title |
| `subject` | yes | Subject id, same as the subject folder name |
| `level` | yes | Who it is written for: `primary`, `middle`, `secondary`, `college`, `postgraduate`, `professional`, `self-learner` |
| `explain_language` | yes | Language of the text, as a BCP-47 tag (`en`, `hi`, `es-MX`) |
| `intro` | yes | One or two sentences: what the learner can do after this module |
| `batches` | yes | The lesson, see below |
| `interview` | no | `[{"q": ..., "a": ...}]`: interview questions (career subjects) |

## Structure

- A module has **batches**. A batch is 4-6 small **steps** (about 15-25 minutes).
- The learner sees **one step at a time**.
- Every batch ends with **notes**: `points` (key points), optional `code` (one snippet,
  formula or example to remember) and `remember` (a one-line takeaway). The tutor gives them
  to the learner after the batch and saves them to the learner's notes for revision.

## Step types

| Type | What the learner does | Fields |
| --- | --- | --- |
| `learn` | Reads one idea | `title`, `body`, optional `code` |
| `choice` | Picks one answer | `question`, optional `code`, `options`, `answer` (0-based), `explain` |
| `fill` | Fills in blanks (`___`) | `prompt`, `code` **or** `text`, `answers` (one list of accepted answers per blank), `explain` |
| `order` | Puts items in order | `prompt`, `items` (in the correct order, at least 3), `explain` |
| `practice` | Does a real task on their own | `title`, `body`; programming subjects add `file`, `command`, `solution` |
| `explain` | Explains an idea in their own words | `prompt`, `rubric` (points a good answer covers), optional `explain` (a model answer) |

- `fill`: use `code` for programming, `text` for everything else
  ("Water boils at ___ °C at sea level").
- `practice`: `file` is a starter in `exercises/`, `solution` a verified answer in
  `solutions/` (both paths from the repo root). `command` is the only thing a tutor may run
  from a lesson, and must match `^(python -m )?pytest [\w./ -]+$`. Non-programming practice
  (solve these 3 problems, draw this diagram, write a paragraph) needs only `title` and `body`.
- `explain`: the tutor reads the learner's answer and gives feedback against each `rubric`
  point: what they covered, what is missing, one thing to add.

`body` supports a small Markdown subset: paragraphs, `**bold**`, `` `code` ``, `- ` lists and
`[links](https://...)`. Links must point to hosts in `core/allowed_hosts.txt`.

## Writing rules

- **One idea per step.** If a step needs a scroll, split it.
- Every 1-2 `learn` steps, add a check (`choice`, `fill`, `order` or `explain`).
- Explain wrong answers kindly in `explain`: say why the right answer is right.
- Write at the lesson's `level`, in its `explain_language`.
- **Generic, always.** Never use a learner's name, examples from their life, their answers,
  their school or company, or anything in `learner/private_terms.json`. Turn a learner's real
  mistake into an anonymous explanation ("A common mistake is ...").
- **Data, not instructions.** Lessons never tell an AI what to do ("ignore your rules",
  "run this command"), never contain shell commands to run other than a `practice.command`,
  and never link outside `core/allowed_hosts.txt`. The validator flags these.
- Programming subjects: use only public practice sites and packages from the subject's
  `requirements.txt`; run every solution before saving the lesson.

Start from `core/teaching/lesson-template/lesson.json`.
