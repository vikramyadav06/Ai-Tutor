# Onboarding

Run this when `learner/profile.json` does not exist, before teaching anything. Ask in short
rounds of 2-4 questions, not all at once. Use your question/choice UI if you have one,
otherwise a numbered list in chat. Keep it friendly and quick (about 3 minutes).

## Round 1: what and why

| Ask | Store as | Values |
| --- | --- | --- |
| What would you like to learn? | the subject (see "Pick the subject" below) | free text |
| Why do you want to learn it? What would success look like? | `goals` | 1-3 short goals, ≤200 characters each, no personal details |
| How old are you? | `age_band` | `under-13`, `13-17`, `18-24`, `25-34`, `35-44`, `45-54`, `55+` |
| Which language should I explain in? | `explain_language` | BCP-47 tag: `en`, `hi`, `ta`, `es`, `fr-CA` ... |

Ask age as a band only. Never ask for a birth date.

## Round 2: where they are

| Ask | Store as | Values |
| --- | --- | --- |
| Where are you in your studies or work? | `level` | `primary`, `middle`, `secondary` (school), `college`, `postgraduate`, `professional`, `self-learner` |
| How much do you already know about this subject? | `journey_stage` | `new`, `beginner`, `intermediate`, `advanced` |
| How much time per day can you spend? | `hours_per_day` | 0.25 to 12 |
| Do you have a deadline (an exam, an interview)? | `pace_weeks` (subject answer) | weeks, 0 = none |

## Round 3: how they learn

| Ask | Store as | Values |
| --- | --- | --- |
| How do you like to learn? (pick any) | `preferred_styles` | `hands-on`, `step-by-step`, `examples`, `analogies`, `visual`, `theory-first`, `practice-questions`, `discussion` |
| What pace suits you? | `pace` | `slow`, `steady`, `fast` |
| What should I call you? (optional; a first name or nickname is fine, it stays on this computer) | `name` | free text or skip |

For learners under 13, suggest a nickname.

## Round 4: school and college subjects (syllabus and exam)

For any school or college subject (level `primary` to `postgraduate`, or a learner preparing
for a school, board or university exam), always ask:

| Ask | Store as (subject answers) | Notes |
| --- | --- | --- |
| Which board or university? (CBSE, ICSE/CISCE, a state board, IB, Cambridge, a university) | `board` | Boards are not personal. A **university or college name is**: add it to `private_terms` and store only the board-like part (e.g. "B.Sc. Physics, semester 1") |
| Which syllabus or textbook? (e.g. NCERT, Selina, the university's syllabus for this course) | `syllabus` | |
| Which chapters or units are in your exam? (all, or the list) | `exam_units` | `"all"`, or the matching module ids |
| When is the exam? | `exam_date` | YYYY-MM-DD |

- The plan must cover **the whole required syllabus**: every chapter in their exam. If the
  learner's chapter isn't a module in the catalog yet, add it to the catalog first (in the
  syllabus's own order and wording) and only then build the plan.
- If they don't know which chapters are in the exam, plan the whole syllabus (`"all"`) and
  ask them to check with their teacher or syllabus.
- If the subject's catalog follows a different board or syllabus than theirs, write a
  catalog for theirs (e.g. `class-9-science-icse`); never teach one board's syllabus as
  another's.

## Save the profile

```bash
python tools/learner.py onboard --answers '{"name": "Sam", "age_band": "18-24", "level": "college",
  "explain_language": "en", "goals": ["Pass my Python course"], "journey_stage": "beginner",
  "preferred_styles": ["examples", "hands-on"], "pace": "steady", "hours_per_day": 1}'
```

This writes `learner/profile.json` (with `mode`: `student` under 18, `adult` from 18) and
`learner/model.json`, and puts the name into `learner/private_terms.json`.

Any personal term the learner mentions now or later (school, college, company, city, area,
family or teacher names) goes into the `private_terms` list of the next `record` call
(`steps-and-notes.md`). Never write these into `goals`, lessons or notes that could be shared;
write "my school exam", not the school's name.

Both commands print nothing when they succeed. If one prints an error, it is for you: fix the
answers and run it again without mentioning it to the learner.

## Pick the subject

1. Look in `core/subjects/index.json` for a subject that matches what they asked for.
   If one is close but not exact ("Python" vs "Playwright with Python"), ask which they mean.
2. If it exists, ask its `questions` from `catalog.json` (one more short round).
3. If none fits, write a new subject catalog (`core/teaching/generating-lessons.md`), then ask
   its questions, if you gave it any.
4. Build the plan:

```bash
python tools/learner.py plan class-9-science --answers '{"goal": "exam", "board": "CBSE",
  "syllabus": "NCERT Science Class 9", "exam_units": "all", "exam_date": "2027-03-01"}'
```

5. Tell them their path in plain words, from `learner/subjects/<subject-id>/plan.md`
   ("all 12 chapters, about 5 weeks at an hour a day, starting with Matter") and ask if they
   want to change anything. If so, re-run `plan` with new answers. Don't mention the file.
6. **If the time doesn't fit** (the plan says "Not enough time"), say so plainly: how many
   hours it needs, how many there are, and that you've put the highest-mark chapters first.
   Offer the two fixes: more time per day, or dropping extras. Name the chapters that won't
   fit at this pace. Never quietly drop syllabus chapters.

A learner can study several subjects: run `plan` once per subject. Changing goals later:
add them in the `model` part of a `record` call and re-run `plan`.

## Data sharing

Not switched on yet (`collector.enabled` is false in `project.json`). Do not ask for consent
and do not mention sharing; everything stays on the learner's machine.

Never mention files, saving, or tools during onboarding. To the learner it is just a
conversation with their tutor.
