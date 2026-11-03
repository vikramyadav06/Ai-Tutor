# The learner model

Everything the tutor knows about a learner lives in `learner/` on their machine. It is
git-ignored and never pushed. It is kept current invisibly: you never mention it, and you
never edit these files by hand. The batch's `record` call (`steps-and-notes.md`) and the
session hooks write them.

| File | What | Written by |
| --- | --- | --- |
| `profile.json` | name (optional), `age_band`, `mode`, `level`, `explain_language`, `hours_per_day`, `sharing`, subjects | `learner.py onboard`, `plan` |
| `model.json` | how this person learns (below) | `learner.py onboard`, `model` |
| `private_terms.json` | every personal term ever mentioned | `record` (`private_terms`) |
| `subjects/<id>/answers.json` | answers to the subject's questions | `learner.py plan` |
| `subjects/<id>/plan.json`, `plan.md` | ordered modules, target dates, status | `learner.py plan`, `progress` |
| `subjects/<id>/notes.md` | revision notes after every batch | `record` (`batch_done`) |
| `subjects/<id>/progress.md` | session history | `record` (`progress_entry`) |
| `sessions/<uuid>.jsonl` | the session log | `record` (`steps`, `moves`, ...) and the hooks |
| `tutor.log`, `pending.jsonl` | background failures and their retry queue | the tools; never shown |

## model.json

| Field | Meaning | Values |
| --- | --- | --- |
| `goals` | why they are learning | ≤10 short texts, ≤200 characters, no personal details |
| `journey_stage` | how far along they are overall | `new`, `beginner`, `intermediate`, `advanced`, `revising` |
| `preferred_styles` | how they like to learn | `hands-on`, `step-by-step`, `examples`, `analogies`, `visual`, `theory-first`, `practice-questions`, `discussion` |
| `pace` | how fast to go | `slow`, `steady`, `fast` |
| `strengths` | topics they have shown they know | topic slugs (`fractions`, `locators`) |
| `weak_areas` | topics to revisit | topic slugs |
| `what_works` | what you have seen help them | ≤10 short texts: "short analogies before code", "a worked example before practice" |

Update it in the `model` part of a batch's `record` call:

```json
"model": {"add": {"weak_areas": ["photosynthesis"], "what_works": ["real-life examples before formulas"]},
          "remove": {"weak_areas": ["locators"]},
          "set": {"pace": "slow", "journey_stage": "intermediate"}}
```

Adding a topic to `strengths` removes it from `weak_areas` and the other way round.

Write `what_works` and `goals` generically: never names, places, schools, companies or
anything in `private_terms.json`.

## When to update

- **Weak area:** they get a check wrong twice, need 2+ hints, or say they're confused.
- **Remove a weak area / add a strength:** 2 correct answers on that topic in a later session.
- **what_works:** a teaching move clearly helped (they got it right right after).
- **pace / journey_stage:** from the patterns in the private context (see `adaptation.md`),
  or when they ask to go slower or faster.
- **progress.md:** a short `progress_entry` in the last `record` call of each session:

```
### YYYY-MM-DD – <module title>
- Learned: ...
- Struggled with: ...
- Next: ...
```
