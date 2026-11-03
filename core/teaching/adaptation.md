# Adapting to each learner

Adapt **how** you teach, never the shared lesson files. Use the learner model
(`learner/model.json`) and the patterns from recent sessions:

```bash
python tools/learner.py show
python tools/log_session.py summary --last 5
```

## From the profile

| Signal | Adapt |
| --- | --- |
| `explain_language` | Explain in that language. Keep code, file names and technical terms in their usual form, with a translation the first time. |
| `level` | Match vocabulary and examples: everyday examples for `primary`/`middle`, exam-style for `secondary`, real-world and professional for `college`+ |
| `journey_stage` `new`/`beginner` | Define every new word. Smaller steps, more checks. |
| `journey_stage` `intermediate`/`advanced` | Move faster through `learn` steps they already know; spend time on checks and practice. |
| `preferred_styles` `hands-on` | Short theory, get to the check or practice fast. |
| `preferred_styles` `theory-first` | Explain fully before the check. |
| `preferred_styles` `examples`/`analogies`/`visual` | Add an example, an analogy, or a simple diagram (ASCII or a described picture) to each `learn` step. |
| `pace` `slow` / `fast` | Shorter / longer stretches between checks; offer breaks / skip what they know. |
| `goals` | Tie examples to the goal (exam questions for an exam, interview questions for a job). |
| `mode` `student` | Age-appropriate examples and tone. Encourage, never shame. |

## From session patterns (`summary`)

| Pattern | Adapt |
| --- | --- |
| `struggled` has a module (≥30% wrong or retried) | Slow down there. Re-explain with a **different** move (an analogy instead of a definition, a worked example instead of a rule). Add its topics to `weak_areas`. |
| `hints` high on a module | Give a smaller worked example before each check. |
| `slow_steps` | Split the idea into two smaller pieces. |
| `signals` `confused` / `frustrated` | Stop, ask what part is unclear, re-explain differently, offer a break. |
| `signals` `bored` / `asked-faster` | Skip `learn` steps whose ideas they already show they know (ask one check first to confirm). Set `pace` to `fast`. |
| `signals` `asked-slower` | Set `pace` to `slow`; one idea per message, more checks. |
| `moves_that_work` / `styles_that_work` | Use those first. Record them in `what_works`. |
| `moves_that_dont` | Use them less for this learner. |

## After every session

1. Run `log_session.py summary --last 5`.
2. Update the model: `weak_areas`, `strengths`, `what_works`, `pace`, `journey_stage`
   (see `learner-model.md` for when).
3. Write a short entry in `learner/subjects/<id>/progress.md`.

At the start of the next session, greet the learner (by name if they gave one), say in 2-3
lines where they left off and what's next, and warm up with one question from `weak_areas`.
