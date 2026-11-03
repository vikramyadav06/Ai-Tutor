# The learner model

Everything the tutor knows about a learner lives in `learner/` on their machine. It is
git-ignored and never pushed. Keep it current silently; mention it in one short line at most
("notes saved").

| File | What | Written by |
| --- | --- | --- |
| `profile.json` | name (optional), `age_band`, `mode`, `level`, `explain_language`, `hours_per_day`, `sharing`, subjects | `learner.py onboard`, `plan` |
| `model.json` | how this person learns (below) | `learner.py onboard`, `model` |
| `private_terms.json` | every personal term ever mentioned | `learner.py add-term` |
| `subjects/<id>/answers.json` | answers to the subject's questions | `learner.py plan` |
| `subjects/<id>/plan.json`, `plan.md` | ordered modules, target dates, status | `learner.py plan`, `progress` |
| `subjects/<id>/notes.md` | revision notes after every batch | `learner.py notes` |
| `subjects/<id>/progress.md` | session history in the learner's words | you, after each session |
| `sessions/<uuid>.jsonl` | the silent session log | `log_session.py` |

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

Update it with `tools/learner.py model`:

```bash
python tools/learner.py model --add weak_areas=photosynthesis
python tools/learner.py model --add strengths=locators --remove weak_areas=locators
python tools/learner.py model --set pace=slow --set journey_stage=intermediate
python tools/learner.py model --add what_works="real-life examples before formulas"
```

Write `what_works` and `goals` generically: never names, places, schools, companies or
anything in `private_terms.json`.

## When to update

- **Weak area:** they get a check wrong twice, need 2+ hints, or say they're confused.
- **Remove a weak area / add a strength:** 2 correct answers on that topic in a later session.
- **what_works:** a teaching move clearly helped (they got it right right after).
- **pace / journey_stage:** after each session, from `log_session.py summary` (see
  `adaptation.md`), or when they ask to go slower or faster.
- **progress.md:** a short entry at the end of each session, newest first:

```
### YYYY-MM-DD – <module title>
- Learned: ...
- Struggled with: ...
- Next: ...
```
