# Archived web app

The browser version of the original Playwright course, kept unchanged as the seed for the
platform website (built in Repo B, Phase 5). It is **not used by the tutor** and its paths
still point at the old `course/` layout, so it does not run from here.

- `index.html`: the single-page web app
- `bundle.js`: offline copy of the course content, built by `build_bundle.py`
- `start.py`: the old terminal onboarding; its plan rules now live in
  `core/subjects/playwright-python/catalog.json` and are applied by `tools/learner.py`
