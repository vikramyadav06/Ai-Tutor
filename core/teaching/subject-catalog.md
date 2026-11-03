# Subject catalog format

Each subject has `core/subjects/<subject-id>/catalog.json` and an entry in
`core/subjects/index.json`. `tools/learner.py plan <subject-id>` builds a learner's plan from
it, and `tools/validate.py` checks it.

```json
{
  "subject": "class-9-science",
  "title": "Class 9 Science",
  "levels": ["secondary"],
  "explain_language": "en",
  "questions": [
    {"id": "goal", "question": "What's your main goal?", "options": [
      {"value": "exam", "label": "Prepare for my exams"},
      {"value": "understand", "label": "Understand the ideas properly"}]},
    {"id": "focus", "question": "Which parts matter most?", "multi": true, "options": [
      {"value": "physics", "label": "Physics"}]}
  ],
  "modules": [
    {"id": "matter", "title": "Matter around us", "hours": 2, "kind": "core", "requires": []},
    {"id": "motion", "title": "Motion", "hours": 3, "kind": "focus", "requires": []}
  ],
  "focus_areas": {
    "physics": {"label": "Physics", "modules": ["motion"]}
  },
  "rules": [
    {"when": {"goal": "exam"}, "add_modules": ["revision"], "reason": "For your goal"},
    {"when": {"prior": "strong"}, "shorten": {"modules": ["matter"], "hours": 1}, "note": "Quick pace"}
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

The plan is: every `core` module, then the learner's chosen focus areas, then whatever the
rules add, each pulling in its `requires` first, in catalog order, with `schedule_last` at the
end. Target dates come from the learner's hours per day.

## A subject that doesn't exist yet

When a learner asks for something with no catalog, the tutor writes one (see
`core/teaching/generating-lessons.md`): a generic outline for the learner's level, with no
personal details, then adds the subject to `index.json` and runs `python tools/validate.py`.
