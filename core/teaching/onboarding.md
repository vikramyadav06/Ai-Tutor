# Onboarding

Run this when `learner/profile.json` does not exist, before teaching anything. Ask in short
rounds of 2-4 questions, not all at once. Use your question/choice UI if you have one,
otherwise a numbered list in chat. Keep it friendly and quick (about 3 minutes).

## Round 0: learned here before? (one question, once)

The very first question, asked once: **"Have you learned with this tutor before, on another
device? If you have your code, paste it here."** (Adults have a learner code `lrn-…`, students
a sync code `sync-…`.)

- **They paste a code:** `python tools/learner.py restore <code>`. It prints nothing when it
  works: everything from their other device is now here (profile, plans, notes, progress,
  their work, the lessons). Skip the rest of onboarding; greet them by name if they gave one
  and pick up where they left off, as at the start of any session (`AGENTS.md` section 1).
  - If it reports that it needs packages: ask in the same moment whether you may install
    them (`python tools/learner.py install-sharing-packages`), then run `restore` again.
  - "doesn't match any saved progress": say "That code didn't work. Could you check it?" and
    let them try once more, or start fresh.
  - "no saved progress was found": say so and start fresh; nothing is lost on their other
    device.
  - "needs-gh-auth": say once, "To bring your progress over, run `gh auth login`, then start
    me again." Record `"gh_login_asked": true`. Their code is kept; it finishes by itself next
    time.
- **No code, or first time:** carry on with Round 1.

## Round 1: age, then what and why

Ask the age band **first** (TECH_SPEC §9): it decides the learner's mode.

| Ask | Store as | Values |
| --- | --- | --- |
| How old are you? | `age_band` | `under-13`, `13-17`, `18-24`, `25-34`, `35-44`, `45-54`, `55+` |
| What would you like to learn? | the subject (see "Pick the subject" below) | free text |
| Why do you want to learn it? What would success look like? | `goals` | 1-3 short goals, ≤200 characters each, no personal details |
| Which language should I explain in? One, or a mix? | `explain_language`, `language_note` | One BCP-47 tag (`en`, `hi`, `ta`, `es`, `fr-CA` ...), or a list for a mix, primary first: `["hi", "en"]` for "Hindi and English". `language_note` (optional, ≤200 characters) says how to mix: "Hindi explanations, English technical terms" |

Ask age as a band only. Never ask for a birth date. Under 18 = **student mode**, 18+ =
**adult mode**. Teaching is identical; only what may be shared differs.


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

## Round 4: school and college subjects (their book, their exam)

**The syllabus comes from the learner, never from memory.** Textbooks change (NCERT replaced
its Class 9 Science book for 2026-27, for example), so what you remember may be out of date.

For any school or college subject (level `primary` to `postgraduate`, or a learner preparing
for a school, board or university exam), always ask:

| Ask | Store as (subject answers) | Notes |
| --- | --- | --- |
| Which board? | `board` | One of `cbse`, `cisce`, `nios`, `ib`, `cambridge`, `state-board`, `university`, `other`. A **university or college name is personal**: never store it; add it to `private_terms` |
| What is your textbook called, and which edition or year is it? | `textbook`, `edition` | As printed on the cover, e.g. "Exploration", "2026-27" |
| Can you send me its list of chapters? Type it, paste it, or send a photo of the contents page | the catalog's modules | One module per chapter, in the book's order, with the book's own titles |
| Which of those chapters are in your exam? (all, or the list) | `exam_units` | `"all"`, or module ids |
| When is the exam? | `exam_date` | YYYY-MM-DD |
| Do you have the official marking scheme (marks per chapter or unit)? | catalog `weightage` | Only from a scheme they give you. Never invent marks; without one, chapters count as equal |

Then:

- **Build the catalog only from their chapter list** (`generating-lessons.md`): board,
  textbook, edition, `"source": "learner"`, `"provisional": false`. The subject id names the
  book, e.g. `class-9-science-exploration`. If a catalog for exactly that board, textbook and
  edition already exists, check its chapters against their list and use it.
- **If they can't provide the list**, build a provisional catalog (`"provisional": true`),
  tell them plainly that the plan is provisional until they check the chapters with their
  teacher, and ask for the contents page again next session. Rebuild the plan once you have it.
- The plan covers **every chapter in their exam**. If the time doesn't fit, say so (step 6
  below). With an official marking scheme, the highest-mark chapters go first; without one,
  chapters keep the book's order.

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
python tools/learner.py plan class-9-science-exploration --answers '{"goal": "exam", "board": "cbse",
  "textbook": "Exploration", "edition": "2026-27", "exam_units": "all", "exam_date": "2027-03-01"}'
```

5. Tell them their path in plain words, from `learner/subjects/<subject-id>/plan.md`
   ("all 13 chapters of your book, about 6 weeks at an hour a day") and ask if they
   want to change anything. If so, re-run `plan` with new answers. Don't mention the file.
6. **If the time doesn't fit** (the plan says "Not enough time"), say so plainly: how many
   hours it needs, how many there are, and how you ordered it: highest-mark chapters first if
   they gave you an official marking scheme, otherwise the book's order (all chapters equal).
   Offer the two fixes: more time per day, or dropping extras. Name the chapters that won't
   fit at this pace. Never quietly drop syllabus chapters.

A learner can study several subjects: run `plan` once per subject. Changing goals later:
add them in the `model` part of a `record` call and re-run `plan`.

## Your code (once, at the end of onboarding)

After the plan is agreed, show every learner their code once, so they can continue on
another device. This is the same moment for everyone (TECH_SPEC §16):

1. `python tools/learner.py sharing-check`. If it lists packages, ask first: "So you can carry
   on from another computer, I'd like to install two small Python packages in this folder.
   Is that OK?" Yes: `python tools/learner.py install-sharing-packages`. No (or the install
   fails): record `"sync": false` and show nothing; never ask again.
2. `python tools/learner.py code` and show it with its warning. Adults get their learner code
   (it also lets them delete shared data later); students get a sync code, which is only for
   continuing on another device and is never sent anywhere.
3. Record `"code_shown": true`. Never show it again unless they ask for it.

If they later say "stop syncing" or "sync again": `"sync": false` / `true` in a `record` call.

## Consent (one question, once)

**Only when `collector.enabled` is `true`** in `project.json`. While it is `false`, never ask
and never mention sharing: everything stays on the learner's machine. (If it is switched on
later, the private context at session start says the question is due; ask it once then.)

Ask it right after the age band (TECH_SPEC §9), at most once ever:

1. Get the example record for their mode: `python tools/learner.py consent-sample`. It is
   built from an invented sample session, never from their data.
2. Ask: "May I share anonymous learning data like this to improve the course? Your name and
   personal details are never shared." Show the example (adults: the shape of what is shared
   about how they learn; students: a record with no id, no time and no free text, that can't
   be linked to them or to any other session). Yes or No; they can change it any time.
3. **If they say yes**, check what sharing needs on this computer:
   `python tools/learner.py sharing-check`. If it lists packages (pynacl, jsonschema), ask in
   the same moment: "To share, I need to install two small Python packages, pynacl and
   jsonschema, in this folder only. Is that OK?"
   - Yes: `python tools/learner.py install-sharing-packages`. If that reports an error, say "I
     couldn't set that up on this computer, so nothing will be shared." and record
     `"sharing": false`.
   - No: nothing is shared. Record `"sharing": false`.
4. Record the answer in the next `record` call: `"sharing": true` (only once the packages are
   there) or `"sharing": false`.
5. Adults have already seen their learner code (Your code, above); don't show it again.
6. Later, "stop sharing" or "share again" → `"sharing": false` / `true` in a `record` call.
   "Delete my data" (adults) → `"delete_request": true`. Students' data can't be deleted
   because nothing links it to them; say so if asked.

If sync or sharing needs GitHub and `gh` isn't signed in, the private context will say so once;
then say, at the end of a batch: "To keep your progress safe across devices, run
`gh auth login` when convenient."
Record `"gh_login_asked": true`. Never ask again; teaching never waits for it.

Never mention files, saving, or tools during onboarding. To the learner it is just a
conversation with their tutor.
