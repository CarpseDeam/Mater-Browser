"""Tests for PaymentBlocker."""
import pytest

from src.agent.payment_blocker import BlockDecision, PaymentBlocker


class TestBlockDecision:
    def test_block_decision_fields(self) -> None:
        decision = BlockDecision(should_block=True, reason="test", confidence=0.9)
        assert decision.should_block is True
        assert decision.reason == "test"
        assert decision.confidence == 0.9

    def test_block_decision_none_reason(self) -> None:
        decision = BlockDecision(should_block=False, reason=None, confidence=0.0)
        assert decision.reason is None


class TestPaymentBlockerMustBlock:
    @pytest.fixture
    def blocker(self) -> PaymentBlocker:
        return PaymentBlocker()

    @pytest.mark.parametrize("url_segment", [
        "/checkout",
        "/payment",
        "/subscribe",
        "/premium",
        "/upgrade",
        "/billing",
    ])
    def test_blocks_payment_urls(self, blocker: PaymentBlocker, url_segment: str) -> None:
        url = f"https://example.com{url_segment}"
        decision = blocker.should_block(url, "Some page content")
        assert decision.should_block is True
        assert decision.reason is not None
        assert decision.confidence > 0.5

    def test_blocks_credit_card_input_by_name(self, blocker: PaymentBlocker) -> None:
        content = '''
        <form>
            <input name="card_number" type="text">
            <input name="cvv" type="text">
            <input name="expiry_date" type="text">
        </form>
        '''
        decision = blocker.should_block("https://example.com/page", content)
        assert decision.should_block is True
        assert decision.confidence > 0.5

    def test_blocks_credit_card_input_by_pattern(self, blocker: PaymentBlocker) -> None:
        content = '''
        <form>
            <input placeholder="Card Number" type="text">
            <input placeholder="MM/YY" type="text">
            <input placeholder="CVC" type="text">
        </form>
        '''
        decision = blocker.should_block("https://example.com/page", content)
        assert decision.should_block is True

    def test_blocks_credit_card_input_by_autocomplete(self, blocker: PaymentBlocker) -> None:
        content = '''
        <form>
            <input autocomplete="cc-number" type="text">
            <input autocomplete="cc-exp" type="text">
            <input autocomplete="cc-csc" type="text">
        </form>
        '''
        decision = blocker.should_block("https://example.com/page", content)
        assert decision.should_block is True

    @pytest.mark.parametrize("button_text", [
        "Complete Purchase",
        "Subscribe Now",
        "Buy Now",
        "Upgrade to Premium",
    ])
    def test_blocks_purchase_buttons(self, blocker: PaymentBlocker, button_text: str) -> None:
        content = f'<button type="submit">{button_text}</button>'
        decision = blocker.should_block("https://example.com/page", content)
        assert decision.should_block is True
        assert decision.reason is not None

    def test_blocks_indeed_premium_upsell(self, blocker: PaymentBlocker) -> None:
        content = '''
        <div class="premium-upsell">
            <h2>Upgrade to Indeed Premium</h2>
            <p>Get more visibility for your applications</p>
            <button>Get Premium</button>
        </div>
        '''
        decision = blocker.should_block("https://indeed.com/premium", content)
        assert decision.should_block is True

    def test_blocks_linkedin_premium_prompt(self, blocker: PaymentBlocker) -> None:
        content = '''
        <div class="premium-subscription">
            <h2>LinkedIn Premium</h2>
            <p>See who viewed your profile</p>
            <button>Try Premium</button>
        </div>
        '''
        decision = blocker.should_block("https://linkedin.com/premium", content)
        assert decision.should_block is True


class TestPaymentBlockerMustAllow:
    @pytest.fixture
    def blocker(self) -> PaymentBlocker:
        return PaymentBlocker()

    @pytest.mark.parametrize("url_segment", [
        "/apply",
        "/submit",
        "/application",
    ])
    def test_allows_job_application_urls(self, blocker: PaymentBlocker, url_segment: str) -> None:
        url = f"https://example.com/jobs{url_segment}"
        content = "<form><button>Submit Application</button></form>"
        decision = blocker.should_block(url, content)
        assert decision.should_block is False

    def test_allows_profile_updates(self, blocker: PaymentBlocker) -> None:
        url = "https://linkedin.com/in/user/edit"
        content = '''
        <form>
            <input name="headline" type="text">
            <input name="summary" type="text">
            <button>Save Profile</button>
        </form>
        '''
        decision = blocker.should_block(url, content)
        assert decision.should_block is False

    def test_allows_normal_navigation(self, blocker: PaymentBlocker) -> None:
        url = "https://indeed.com/jobs?q=software+engineer"
        content = '''
        <div class="job-list">
            <div class="job-card">Software Engineer at Company</div>
        </div>
        '''
        decision = blocker.should_block(url, content)
        assert decision.should_block is False

    def test_allows_salary_info_paywall_display(self, blocker: PaymentBlocker) -> None:
        url = "https://example.com/jobs/123"
        content = '''
        <div class="salary-info">
            <p>Estimated salary: $80,000 - $120,000</p>
            <p class="premium-hint">See detailed salary insights with Premium</p>
        </div>
        '''
        decision = blocker.should_block(url, content)
        assert decision.should_block is False


class TestPaymentBlockerEdgeCases:
    @pytest.fixture
    def blocker(self) -> PaymentBlocker:
        return PaymentBlocker()

    def test_mixed_signals_apply_and_upgrade_allows(self, blocker: PaymentBlocker) -> None:
        url = "https://example.com/jobs/apply"
        content = '''
        <form id="application-form">
            <input name="resume" type="file">
            <button type="submit">Submit Application</button>
        </form>
        <aside class="sidebar">
            <button>Upgrade to Premium</button>
        </aside>
        '''
        decision = blocker.should_block(url, content)
        assert decision.should_block is False

    def test_premium_url_but_job_listing_content_allows(self, blocker: PaymentBlocker) -> None:
        url = "https://example.com/premium-jobs/listing/12345"
        content = '''
        <div class="job-listing">
            <h1>Senior Software Engineer</h1>
            <p>We are looking for a talented engineer...</p>
            <button>Apply Now</button>
        </div>
        '''
        decision = blocker.should_block(url, content)
        assert decision.should_block is False

    def test_confirmation_page_after_application_allows(self, blocker: PaymentBlocker) -> None:
        url = "https://example.com/application/confirmed"
        content = '''
        <div class="confirmation">
            <h1>Application Submitted!</h1>
            <p>Thank you for applying to Software Engineer position.</p>
            <p>You will receive a confirmation email shortly.</p>
        </div>
        '''
        decision = blocker.should_block(url, content)
        assert decision.should_block is False


class TestPaymentBlockerDeterminism:
    def test_same_input_same_output(self) -> None:
        blocker = PaymentBlocker()
        url = "https://example.com/checkout"
        content = "<button>Complete Purchase</button>"

        results = [blocker.should_block(url, content) for _ in range(10)]

        first = results[0]
        for result in results[1:]:
            assert result.should_block == first.should_block
            assert result.reason == first.reason
            assert result.confidence == first.confidence


class TestPaymentBlockerConfidence:
    @pytest.fixture
    def blocker(self) -> PaymentBlocker:
        return PaymentBlocker()

    def test_confidence_range_valid(self, blocker: PaymentBlocker) -> None:
        test_cases = [
            ("https://example.com/checkout", "<button>Buy Now</button>"),
            ("https://example.com/jobs/apply", "<button>Submit</button>"),
            ("https://example.com/page", "Normal content"),
        ]
        for url, content in test_cases:
            decision = blocker.should_block(url, content)
            assert 0.0 <= decision.confidence <= 1.0
