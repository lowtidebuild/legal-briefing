from pipeline.render.manifest import SITE_URL, _article_url


def test_article_url_rejects_unsafe_event_key():
    assert _article_url("../escape") == SITE_URL
    assert _article_url("safe_key_2026q3") == f"{SITE_URL}article/safe_key_2026q3.html"
