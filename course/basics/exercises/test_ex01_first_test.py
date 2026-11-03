r"""
Exercise 01 – Your first test

Task:
    Log in to https://www.saucedemo.com as standard_user / secret_sauce.

Acceptance criteria:
    - After login the URL ends with "inventory.html".
    - The page title is "Swag Labs".
    - The test passes headless and with --headed.

Hints:
    - The inputs have placeholders "Username" and "Password": page.get_by_placeholder(...)
    - The login button: page.get_by_role("button", name="Login")
    - expect(page).to_have_url(re.compile(r"inventory\.html$"))

Run:
    pytest my-work/basics -v --headed
"""
import re

import pytest
from playwright.sync_api import Page, expect


def test_login_shows_inventory(page: Page):
    pytest.skip("TODO: remove this line when you start")
    # TODO: open saucedemo, log in, then check the URL and the title
