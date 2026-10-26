"""
UI Automation Tests — Playwright (Python)
Requires: pip install playwright pytest-playwright
          playwright install chromium

Run: pytest tests/ui/test_ui.py -v --base-url http://localhost:5000

Note: These tests target a minimal HTML UI served by the Flask app at /ui.
"""

import re
import pytest
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
# 1. Open application / login
# ---------------------------------------------------------------------------
class TestLogin:
    def test_app_loads(self, page: Page):
        page.goto("/ui")
        expect(page).to_have_title(re.compile("MiniPay", re.IGNORECASE))

    def test_login_page_present(self, page: Page):
        page.goto("/ui/login")
        expect(page.get_by_role("textbox", name=re.compile("api key", re.IGNORECASE))).to_be_visible()

    def test_login_success(self, page: Page):
        page.goto("/ui/login")
        page.get_by_label(re.compile("api key", re.IGNORECASE)).fill("changeme")
        page.get_by_role("button", name=re.compile("login|sign in", re.IGNORECASE)).click()
        expect(page).to_have_url(re.compile(r"/ui/dashboard|/ui$"))


# ---------------------------------------------------------------------------
# 2. Search for a transaction
# ---------------------------------------------------------------------------
class TestTransactionSearch:
    def test_search_existing_transaction(self, page: Page):
        page.goto("/ui")
        search_input = page.get_by_placeholder(re.compile("transaction ref", re.IGNORECASE))
        search_input.fill("TXN-TEST001")
        page.keyboard.press("Enter")
        # Either found or not-found message — no 500 error
        expect(page.locator("body")).not_to_contain_text("500")
        expect(page.locator("body")).not_to_contain_text("Internal Server Error")

    def test_search_unknown_transaction_shows_not_found(self, page: Page):
        page.goto("/ui")
        page.get_by_placeholder(re.compile("transaction ref", re.IGNORECASE)).fill("TXN-DOESNOTEXIST999")
        page.keyboard.press("Enter")
        expect(page.locator("[data-testid='search-result'], .search-result, main")).to_contain_text(
            re.compile("not found|no results|404", re.IGNORECASE)
        )


# ---------------------------------------------------------------------------
# 3. Create / submit a payment
# ---------------------------------------------------------------------------
class TestCreatePayment:
    def test_payment_form_visible(self, page: Page):
        page.goto("/ui/payments/new")
        expect(page.get_by_label(re.compile("amount", re.IGNORECASE))).to_be_visible()
        expect(page.get_by_label(re.compile("customer", re.IGNORECASE))).to_be_visible()

    def test_submit_payment_success(self, page: Page):
        page.goto("/ui/payments/new")
        page.get_by_label(re.compile("customer id", re.IGNORECASE)).fill("1")
        page.get_by_label(re.compile("amount", re.IGNORECASE)).fill("100.00")
        page.get_by_role("button", name=re.compile("submit|pay|create", re.IGNORECASE)).click()
        # Should show success state
        expect(page.locator("body")).to_contain_text(
            re.compile("success|created|processing", re.IGNORECASE)
        )

    # 4. Validate successful result
    def test_payment_result_shows_transaction_ref(self, page: Page):
        page.goto("/ui/payments/new")
        page.get_by_label(re.compile("customer id", re.IGNORECASE)).fill("1")
        page.get_by_label(re.compile("amount", re.IGNORECASE)).fill("50.00")
        page.get_by_role("button", name=re.compile("submit|pay|create", re.IGNORECASE)).click()
        expect(page.locator("body")).to_contain_text(re.compile(r"TXN", re.IGNORECASE))


# ---------------------------------------------------------------------------
# 5. Negative / error scenarios
# ---------------------------------------------------------------------------
class TestNegativeScenarios:
    def test_submit_payment_missing_amount(self, page: Page):
        page.goto("/ui/payments/new")
        page.get_by_label(re.compile("customer id", re.IGNORECASE)).fill("1")
        # Leave amount blank
        page.get_by_role("button", name=re.compile("submit|pay|create", re.IGNORECASE)).click()
        # Should show validation error, not a server error
        expect(page.locator("body")).to_contain_text(
            re.compile("required|amount|invalid", re.IGNORECASE)
        )
        expect(page.locator("body")).not_to_contain_text("500")

    def test_submit_payment_negative_amount(self, page: Page):
        page.goto("/ui/payments/new")
        page.get_by_label(re.compile("customer id", re.IGNORECASE)).fill("1")
        page.get_by_label(re.compile("amount", re.IGNORECASE)).fill("-50")
        page.get_by_role("button", name=re.compile("submit|pay|create", re.IGNORECASE)).click()
        expect(page.locator("body")).to_contain_text(
            re.compile("invalid|positive|error", re.IGNORECASE)
        )
