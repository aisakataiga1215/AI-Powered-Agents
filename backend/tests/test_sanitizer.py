"""PII sanitizer tests.

Covers each PII pattern individually and a realistic interview sample.
Business signal must survive; identifying tokens must not.
"""

import pytest

from app.utils.sanitizer import sanitize_text


def test_empty_text_returns_clean_flag():
    assert sanitize_text("") == ("", False)


def test_none_input_returns_clean_flag():
    assert sanitize_text(None) == ("", False)


def test_plain_text_is_untouched():
    text = "用户希望产品支持离线导出功能,并改进 UI 交互。"
    masked, contains_pii = sanitize_text(text)
    assert masked == text
    assert contains_pii is False


def test_email_is_redacted():
    masked, contains_pii = sanitize_text("Contact me at alice.smith+work@example.co.uk anytime.")
    assert "alice.smith+work@example.co.uk" not in masked
    assert "[REDACTED:email]" in masked
    assert contains_pii is True


def test_mailto_uri_is_redacted():
    masked, contains_pii = sanitize_text("Reach out: mailto:user@example.com?subject=Hi")
    assert "user@example.com" not in masked
    assert "[REDACTED:mailto]" in masked
    assert contains_pii is True


def test_cn_mobile_plain_is_redacted():
    masked, contains_pii = sanitize_text("我的手机号是 13812345678,有空联系。")
    assert "13812345678" not in masked
    assert "[REDACTED:phone]" in masked
    assert contains_pii is True


def test_cn_mobile_with_country_code_is_redacted():
    masked, contains_pii = sanitize_text("Call +86 138 1234 5678 for details.")
    assert "138" not in masked.replace("[REDACTED:phone]", "")
    assert "[REDACTED:phone]" in masked
    assert contains_pii is True


def test_cn_mobile_with_zero_prefix_is_redacted():
    masked, contains_pii = sanitize_text("Phone: 008613812345678")
    assert "13812345678" not in masked
    assert "[REDACTED:phone]" in masked
    assert contains_pii is True


def test_international_phone_is_redacted():
    masked, contains_pii = sanitize_text("Office line: +1 (415) 555-2671 ext 12")
    assert "415" not in masked.replace("[REDACTED:phone]", "")
    assert "[REDACTED:phone]" in masked
    assert contains_pii is True


def test_cn_id_card_is_redacted():
    masked, contains_pii = sanitize_text("身份证号:11010519491231002X,请核对。")
    assert "11010519491231002X" not in masked
    assert "[REDACTED:id]" in masked
    assert contains_pii is True


def test_cn_id_card_lowercase_x_is_redacted():
    masked, contains_pii = sanitize_text("ID 110105194912310021,record kept.")
    assert "110105194912310021" not in masked
    assert "[REDACTED:id]" in masked
    assert contains_pii is True


def test_cn_name_with_honorific_is_redacted():
    masked, contains_pii = sanitize_text("访谈对象:张伟先生表示对新功能很期待。")
    assert "张伟" not in masked
    assert "[REDACTED:name]" in masked
    assert "先生" in masked
    assert contains_pii is True


def test_cn_name_with_title_honorific_is_redacted():
    masked, contains_pii = sanitize_text("欧阳娜娜总监给出了具体建议。")
    assert "欧阳娜娜" not in masked
    assert "[REDACTED:name]" in masked
    assert "总监" in masked
    assert contains_pii is True


def test_unrelated_chinese_text_is_preserved():
    text = "我们计划在下季度发布新版本,功能包括离线模式和团队协作。"
    masked, contains_pii = sanitize_text(text)
    assert masked == text
    assert contains_pii is False


def test_full_interview_sample_preserves_business_content():
    transcript = (
        "受访者:李娜女士,联系电话 13800001234,邮箱 li.na@example.com。\n"
        "她身份证号 11010519800101123X。\n"
        "她提到:目前产品缺乏对企业 SSO 的支持,希望增加细粒度权限控制,"
        "并希望团队协作中可以看到改动历史。"
    )
    masked, contains_pii = sanitize_text(transcript)

    # PII tokens are gone.
    assert "李娜" not in masked
    assert "13800001234" not in masked
    assert "li.na@example.com" not in masked
    assert "11010519800101123X" not in masked

    # Each placeholder is present.
    assert "[REDACTED:name]" in masked
    assert "[REDACTED:phone]" in masked
    assert "[REDACTED:email]" in masked
    assert "[REDACTED:id]" in masked

    # Business signal survives intact.
    assert "企业 SSO" in masked
    assert "细粒度权限控制" in masked
    assert "团队协作" in masked
    assert "改动历史" in masked

    assert contains_pii is True


def test_multiple_emails_set_flag_once():
    masked, contains_pii = sanitize_text("a@x.com and b@y.org reached out")
    assert masked.count("[REDACTED:email]") == 2
    assert contains_pii is True


@pytest.mark.parametrize(
    "fragment",
    [
        "version 1.2.3.4 released",
        "build #12345 succeeded",
        "see issue 9876",
    ],
)
def test_version_like_numbers_are_not_misread_as_phones(fragment):
    masked, contains_pii = sanitize_text(fragment)
    assert "[REDACTED:phone]" not in masked
    assert contains_pii is False
