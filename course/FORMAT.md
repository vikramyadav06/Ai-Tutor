# Lesson format

Every module lives in `course/<module-id>/` and has one content file, `lesson.json`.
The web app (`index.html`), AI tutors and human readers all use this same file, so every
learner gets exactly the same content.

## Structure
- A module has **batches**. A batch is 4-6 small **steps** (~15-25 minutes).
- The learner sees **one step at a time**.
- After each batch the learner gets its **notes**: key points, one code snippet and a
  one-line takeaway. Notes are collected on the web app's Notes page for revision.
- `interview` (optional) holds interview questions for the module.

## Step types
| Type | What the learner does | Fields |
| --- | --- | --- |
| `learn` | Reads one idea | `title`, `body`, optional `code` |
| `choice` | Picks one answer | `question`, optional `code`, `options`, `answer` (0-based), `explain` |
| `fill` | Types into code blanks (`___`) | `prompt`, `code`, `answers` (list of accepted strings per blank), `explain` |
| `order` | Arranges steps in order | `prompt`, `items` (correct order), `explain` |
| `practice` | Writes and runs real code locally (optional on the web) | `title`, `body`, `file`, `command`, `solution` |

`body` supports a small Markdown subset: paragraphs, `**bold**`, `` `code` ``,
`- ` lists and `[links](https://...)`.

## Writing rules
- One idea per step. If a step needs a scroll, split it.
- Every 1-2 `learn` steps, add a check (`choice`, `fill` or `order`).
- Explain wrong answers kindly in `explain`.
- Use only public practice sites and packages from `requirements.txt`.
- `practice` exercises have a starter in `exercises/` and a verified solution in `solutions/`.
- After editing any lesson, run `python tools/build_bundle.py` so the offline copy of the
  web app (opened by double-clicking `index.html`) gets the new content.
