"""
Exercise 01 – Smoke test

Task:
    Open https://example.com and check that the page title is "Example Domain".

Acceptance criteria:
    - The test passes with `pytest my-work/setup -v`.

Hints:
    - Ask for the `page` fixture as a test argument.
    - page.goto(url) opens a URL.
    - expect(page).to_have_title("...") checks the title.
"""
import pytest
from playwright.sync_api import Page, expect


def test_smoke(page: Page):
    pytest.skip("TODO: remove this line when you start")
    # TODO: open the page and check its title
