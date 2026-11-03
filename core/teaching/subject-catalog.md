# Subject catalog format

Each subject has `core/subjects/<subject-id>/catalog.json` and an entry in
`core/subjects/index.json`. `tools/learner.py plan <subject-id>` builds a learner's plan from
it, and `tools/validate.py` checks it.

```json
{
  "subject": "class-9-science-exploration",
  "title": "Class 9 Science (Exploration, 2026-27)",
  "levels": ["secondary"],
  "explain_language": "en",
  "syllabus": {"board": "cbse", "textbook": "Exploration", "edition": "2026-27",
               "source": "learner", "provisional": false},
  "questions": [
    {"id": "goal", "question": "What's your main goal?", "options": [
      {"value": "exam", "label": "Prepare for my exams"},
      {"value": "understand", "label": "Understand the ideas properly"}]},
    {"id": "focus", "question": "Do you want extra practice questions?", "multi": true, "options": [
      {"value": "practice", "label": "Yes"}]}
  ],
  "modules": [
    {"id": "chapter-01", "title": "<chapter 1 title, as printed>", "chapter": 1, "hours": 2, "kind": "core", "requires": []},
    {"id": "chapter-02", "title": "<chapter 2 title, as printed>", "chapter": 2, "hours": 3, "kind": "core", "requires": []},
    {"id": "extra-practice", "title": "Extra practice questions", "hours": 3, "kind": "focus", "requires": []}
  ],
  "focus_areas": {
    "practice": {"label": "Extra practice questions", "modules": ["extra-practice"]}
  },
  "rules": [
    {"when": {"goal": "exam"}, "add_modules": ["revision"], "reason": "For your goal"}
  ],
  "schedule_last": ["revision"]
}
```

| Field | Meaning |
| --- | --- |
| `questions` | Subject-specific onboarding questions, asked after the universal ones. `multi: true` = several answers. Answers are checked against `options`. Optional. |
| `modules[]` | `id` (folder name), `title`, `hours`, `kind`, `requires` (module ids that come first) |
| `kind` | `core`: in every plan. `focus`: added when the learner picks its focus area. `optional`: added only by a rule |
| `focus_areas` | Groups of modules the learner can pick with the `focus` question |
| `rules[]` | `when`: answers that must all match (a value or a list of allowed values). Then `add_modules`, `add_focus` (with `reason`), and/or `shorten` (cut `hours` from those modules, with `note`) |
| `schedule_last` | Modules that always go at the end of the plan |
| `syllabus` | School and college subjects: `board` (`cbse`, `cisce`, `nios`, `ib`, `cambridge`, `state-board`, `university`, `other`; never an institution's name), `textbook`, `edition`, `source` (`learner`: their contents page; `official`: an official syllabus they gave you), `provisional` (true until the learner has given their chapter list), optional `marking_scheme` (`{"source": ...}`, only if they gave you an official one). One catalog per board, textbook and edition |
| `chapter` | The chapter number in the learner's book |
| `weightage` | Exam marks for a chapter, **only** from the official marking scheme in `syllabus.marking_scheme`. Never from memory. Without it, chapters count as equal |

For school and college subjects, **one module = one chapter of the learner's own book**, in
its order and with its titles, so "which chapters are in your exam" maps straight to module
ids. Don't invent `requires` between chapters. Practice and revision modules are `focus` or
`optional`. The validator rejects weightage without a marking scheme, a syllabus `source`
other than `learner` or `official`, and boards outside the list.

Exam answers (`board`, `textbook`, `edition`, `exam_units`, `exam_date`) change the plan:
the board, textbook and edition must match the catalog's `syllabus`; with
`exam_units`, the plan covers exactly those chapters (plus anything they require); with an
`exam_date` (or `pace_weeks`) that's too close, it reorders by weightage (only with a marking
scheme) and marks what won't fit, so the tutor can tell the learner. A provisional catalog
makes a provisional plan, and the tutor says so.

The plan is: every `core` module (or, if the learner listed their exam chapters, exactly
those), then the learner's chosen focus areas, then whatever the
rules add, each pulling in its `requires` first, in catalog order, with `schedule_last` at the
end. Target dates come from the learner's hours per day.

## A subject that doesn't exist yet

When a learner asks for something with no catalog, the tutor writes one (see
`core/teaching/generating-lessons.md`): a generic outline for the learner's level, with no
personal details, then adds the subject to `index.json` and runs `python tools/validate.py`.
