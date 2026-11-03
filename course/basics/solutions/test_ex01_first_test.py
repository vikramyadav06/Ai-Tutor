"""Reference solution for Exercise 01. Try the exercise yourself first!"""
import re

from playwright.sync_api import Page, expect


def test_login_shows_inventory(page: Page):
    page.goto("https://www.saucedemo.com")
    page.get_by_placeholder("Username").fill("standard_user")
    page.get_by_placeholder("Password").fill("secret_sauce")
    page.get_by_role("button", name="Login").click()

    expect(page).to_have_url(re.compile(r"inventory\.html$"))
    expect(page).to_have_title("Swag Labs")
