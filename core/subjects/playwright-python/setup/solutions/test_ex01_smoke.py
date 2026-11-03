"""Reference solution for Exercise 01. Try the exercise yourself first!"""
from playwright.sync_api import Page, expect


def test_smoke(page: Page):
    page.goto("https://example.com")
    expect(page).to_have_title("Example Domain")
