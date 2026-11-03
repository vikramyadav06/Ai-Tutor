# Playwright with Python – Full Curriculum

This is the full course outline. You don't need all of it: the tutor asks a few questions and builds a personal plan (`learner/subjects/playwright-python/plan.md`) with only the modules that fit your role, goal and time. Module ids match `catalog.json` in this folder.

## Setup (~1 hour)

- Install Python 3.11+, VS Code (Python + Playwright extensions), Git
- Create a virtual env: `python -m venv venv` and activate it
- `pip install pytest-playwright pytest-xdist pytest-rerunfailures allure-pytest axe-playwright-python python-dotenv`
- `playwright install --with-deps` (downloads Chromium, Firefox, WebKit)
- Practice apps: saucedemo.com (UI), restful-booker (API), the-internet.herokuapp.com (edge cases)

**Target project structure:**

```
<repo>/
├── core/subjects/playwright-python/  # shareable lessons, exercises, solutions (one folder per module)
├── my-work/          # your exercise code, one folder per module
├── pages/            # Page Objects (login_page.py, cart_page.py) – from the POM module
├── tests/
│   ├── ui/           # UI tests
│   ├── api/          # API tests
│   └── visual/       # visual + accessibility tests
├── utils/            # helpers, test data, API clients
├── test_data/        # JSON/CSV data
├── conftest.py       # fixtures: base_url, auth, browser context args
├── pytest.ini        # markers, default CLI options
├── requirements.txt
├── .env.example      # URLs, test users (never real secrets)
└── .github/workflows/playwright.yml
```

## Part 1 – Core Playwright + framework

| # | Topic | Learn | Build (done when green) |
| --- | --- | --- | --- |
| 1 | Basics & architecture | Browser → Context → Page model; sync vs async API; `playwright codegen <url>`; headed vs headless; `--headed`, `--slowmo` | First test with the `page` fixture: open saucedemo, log in, assert page title |
| 2 | Locators | `get_by_role`, `get_by_label`, `get_by_text`, `get_by_placeholder`, `get_by_test_id`; CSS/XPath as fallback; `.filter(has_text=)`, `.nth()`, chaining; strict mode | Locate every element on login + inventory pages using role-based locators only |
| 3 | Actions & tricky UI | `click`, `fill`, `press`, `check`, `select_option`, `hover`, `drag_to`; uploads (`set_input_files`), downloads (`expect_download`); iframes (`frame_locator`); new tabs (`context.expect_page`); alerts (`page.on("dialog")`) | the-internet.herokuapp.com: iframe, JS alerts, file upload/download, multiple windows |
| 4 | Assertions & waiting | Auto-waiting; `expect(...).to_be_visible / to_have_text / to_have_count / to_have_url`; timeouts; `wait_for_response`, `wait_for_load_state`; why no `time.sleep` | Add web-first assertions to your earlier tests; delete every sleep |
| 5 | pytest-playwright deep dive | Built-in fixtures (`page`, `context`, `browser`, `browser_context_args`); conftest + scopes; markers; `parametrize`; CLI: `--browser`, `--base-url`, `--screenshot`, `--video`, `--tracing`; `pytest.ini` | Data-driven login test from JSON: valid, locked-out, wrong password |
| 6 | Page Object Model | `BasePage`, one class per page, fixtures that return page objects; config via `.env`; test data files; logging | Refactor all tests to POM; full flow: login → add to cart → checkout → order confirmation |
| 7 | Auth, sessions & debugging | `context.storage_state(path=)` and reuse; session-scoped login fixture; two users in one test with two contexts; Trace Viewer (`--tracing retain-on-failure`, `playwright show-trace`); `PWDEBUG=1`, `page.pause()` | Log in once per run and reuse state; break a test on purpose and diagnose it from the trace |


## Part 2 – Advanced testing, cross-browser/device, CI

| # | Topic | Learn | Build (done when green) |
| --- | --- | --- | --- |
| 8 | API testing | `APIRequestContext` (`playwright.request.new_context`, `page.request`); GET/POST/PUT/DELETE; status, headers and JSON assertions; token auth; API + UI hybrid | CRUD suite on restful-booker + one hybrid test |
| 9 | Network control | `page.route()` to mock, modify or block requests; `wait_for_response`; HAR record and replay (`route_from_har`) | Mock an empty product list and an API 500 error; block images to speed up a test |
| 10 | Visual & accessibility | Screenshots (full page, element, masking dynamic parts); baseline comparison with a plugin such as `pytest-playwright-visual`; `axe-playwright-python` scans; `to_match_aria_snapshot` | Visual baselines for 3 pages; axe scan that fails on serious/critical issues |
| 11 | Cross-browser | `--browser chromium --browser firefox --browser webkit`; `--browser-channel chrome` / `msedge`; `@pytest.mark.skip_browser` / `only_browser`; engine differences | Full suite passing on 3 engines + Chrome + Edge locally |
| 12 | Cross-device | `--device "iPhone 13"`; `playwright.devices`; context args: `viewport`, `is_mobile`, `has_touch`, `locale`, `timezone_id`, `geolocation`, `color_scheme`, `permissions`; `tap()`; responsive checks | Mobile pack on iPhone, Pixel and iPad emulation, marked `@pytest.mark.mobile`; one dark-mode test |
| 13 | Parallel runs & Allure | `pytest-xdist` (`-n auto`) and test isolation; retries with `pytest-rerunfailures`; `--alluredir`; Allure steps, severity, attachments (screenshot + trace on failure via a hook) | Parallel run in under half the serial time; Allure report with failure attachments |
| 14 | GitHub Actions CI | Workflow YAML; matrix `os × browser` + a device job; pip cache; `playwright install --with-deps`; GitHub Secrets; upload traces as artifacts; publish Allure to GitHub Pages; PR + nightly triggers | Green matrix run, status badge and live Allure report link in README |


## Cross-browser & cross-device cheat sheet

| Goal | Command |
| --- | --- |
| All 3 engines | `pytest --browser chromium --browser firefox --browser webkit` |
| Real Chrome / Edge | `pytest --browser-channel chrome` (or `msedge`) |
| Emulate a phone | `pytest --device "iPhone 13"` or `--device "Pixel 7"` |
| Mobile tests only | `pytest -m mobile` |
| Parallel + report | `pytest -n auto --alluredir=allure-results` |
| Debug a failure | `pytest --headed --tracing retain-on-failure`, then `playwright show-trace <trace.zip>` |

**Custom device settings in `conftest.py`:**

```python
import pytest

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, playwright):
    return {
        **browser_context_args,
        **playwright.devices["Pixel 7"],   # viewport, user agent, touch, mobile
        "locale": "en-IN",
        "timezone_id": "Asia/Kolkata",
        "color_scheme": "dark",
    }
```

**GitHub Actions matrix (`.github/workflows/playwright.yml`):**

```yaml
name: Playwright Tests
on:
  push:
  pull_request:
  schedule:
    - cron: "30 20 * * *"   # nightly
jobs:
  desktop:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        browser: [chromium, firefox, webkit]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements.txt
      - run: playwright install --with-deps ${{ matrix.browser }}
      - run: pytest --browser ${{ matrix.browser }} -n auto --alluredir=allure-results --tracing retain-on-failure
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: results-${{ matrix.os }}-${{ matrix.browser }}
          path: |
            allure-results
            test-results
  mobile:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        device: ["iPhone 13", "Pixel 7", "iPad Pro 11"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements.txt
      - run: playwright install --with-deps
      - run: pytest -m mobile --device "${{ matrix.device }}"
```

**Limit to know:** emulation covers viewport, touch, user agent and device settings, not real phone hardware. Real devices need a cloud grid such as BrowserStack or LambdaTest, which you can add later with no test rewrites.

## Portfolio project & interview prep (job-switch and career-start goals)

**README must show:**

- One-line summary + tech stack badges (Python, Playwright, pytest, Allure, GitHub Actions)
- CI status badge + link to the live Allure report on GitHub Pages
- Coverage list: UI, API, hybrid, visual, accessibility, auth reuse, cross-browser, mobile emulation
- Folder structure + how to run locally (3 commands)
- Screenshot of the Allure dashboard and a Trace Viewer failure
- Short "Design decisions" section: why POM, why storage_state, why matrix CI

**Top interview questions to practise (answer each out loud in 1–2 minutes):**

1. Playwright vs Selenium: architecture, auto-waiting, speed, browser support.
2. Browser vs BrowserContext vs Page, and why contexts give test isolation.
3. How auto-waiting and web-first assertions remove flaky waits.
4. Your locator strategy and why role-based locators come first.
5. How you reuse login across tests (storage_state + session fixture).
6. How you run cross-browser and mobile tests, and the limits of emulation.
7. How you mock APIs and when you would test via API instead of UI.
8. How you debug a failure that only happens in CI (traces, videos, artifacts).
9. Parallel execution with xdist: what breaks and how you keep tests independent.
10. Walk through your framework and CI pipeline end to end.

## Resources

| Resource | Use it for |
| --- | --- |
| [Playwright Python docs](https://playwright.dev/python/docs/intro) | Primary reference |
| [pytest plugin reference](https://playwright.dev/python/docs/test-runners) | CLI flags, fixtures, browser/device options |
| [Emulation guide](https://playwright.dev/python/docs/emulation) | Devices, locale, geolocation, color scheme |
| [CI guide](https://playwright.dev/python/docs/ci) | GitHub Actions setup |
| [Allure pytest docs](https://allurereport.org/docs/pytest/) | Steps, attachments, reports |
| [saucedemo.com](https://www.saucedemo.com) | UI practice |
| [the-internet.herokuapp.com](https://the-internet.herokuapp.com) | Iframes, alerts, uploads, windows |
| [restful-booker](https://restful-booker.herokuapp.com/apidoc/index.html) | API practice |
