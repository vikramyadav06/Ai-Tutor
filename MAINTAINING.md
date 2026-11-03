# Maintaining the course

Learners' AI tutors send new and improved lessons as pull requests (PRs). The maintainer,
or the maintainer's own AI agent, reviews and merges them. Merged lessons go live on the
website for everyone and no longer need an agent.

To have your agent do it, open this repo in Claude Code (or any agent) and say:
**"Review the open course pull requests following MAINTAINING.md."**

## One-time setup
1. Fill in `project.json`: `upstream_repo` (e.g. `your-name/playwright-course`) and `website`.
2. GitHub → **Settings → Pages**: deploy from branch `main`, folder `/ (root)`.
3. GitHub → **Settings → Branches → Add rule** for `main`: require the **Course checks**
   status check to pass before merging. Broken lessons then can't be merged by accident.
4. Install the GitHub CLI and sign in: `gh auth login`.

## Reviewing pull requests

List them: `gh pr list --state open`

For each PR:

1. **Automatic checks**: `gh pr checks <n>`. "Course checks" runs the format validator, makes
   sure only course files changed, and runs every reference solution in a real browser.
   If it's red, comment with the failing part (`gh pr checks <n>` links the log) and stop.
2. **What changed**: `gh pr diff <n>`. Expect only `course/<id>/…`, `course/bundle.js`,
   `course/catalog.json` and a README status line. Anything else needs a closer look.
3. **Content review**, step by step through `lesson.json`:
   - Facts match the official docs (playwright.dev/python). API names and options exist.
   - One idea per step; a check (choice, fill, order) every 1-2 learn steps.
   - Wrong-answer explanations teach something; options aren't trick questions.
   - Each batch has notes: points, snippet, one-line takeaway.
   - Exercises use only public practice sites and packages from `requirements.txt`.
   - No personal details (names, scores, company names), no secrets, no unknown links.
   - Not a duplicate of an existing module or another open PR.
4. **Try it (optional but recommended for new modules)**: `gh pr checkout <n>`, open
   `index.html`, click through the module, then `git switch main`.
5. **Decide**
   - Good: `gh pr merge <n> --squash --delete-branch`.
   - Needs changes: `gh pr review <n> --request-changes --body "<specific fixes>"`.
     The contributor's AI tutor reads the comments next session and pushes fixes.
   - Duplicate or off-topic: `gh pr close <n> --comment "<why>"`.

## After merging
- Change the module's README status from `Draft` to `Ready` once at least one learner has
  completed it and its checks are green.
- If two PRs touched `course/bundle.js`, the second may conflict. Ask its author's agent to
  rebase, or check it out, run `python tools/build_bundle.py`, commit and push.

## Review guidelines for an AI reviewer
- Never merge with failing checks or with files outside course content unless the maintainer says so.
- Prefer requesting changes over rewriting a contributor's lesson yourself.
- Summarise for the maintainer at the end: PRs merged, changes requested (and why), closed.
