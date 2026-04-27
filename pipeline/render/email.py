from __future__ import annotations

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline.models import BriefingNode

CATEGORY_ORDER = [
    "IP",
    "CONSUMER_MONETIZATION",
    "CONTENT_AGE",
    "PRIVACY_SECURITY",
    "PLATFORM_PUBLISHING",
    "AI_EMERGING",
    "MA_CORP_ANTITRUST",
    "ESPORTS_MARKETING",
    "LABOR_EMPLOYMENT",
    "ETC",
]

CATEGORY_LABELS = {
    "AI_EMERGING": "AI / 신기술",
    "CONSUMER_MONETIZATION": "소비자 / 과금",
    "CONTENT_AGE": "콘텐츠 / 연령등급",
    "ESPORTS_MARKETING": "e스포츠 / 마케팅",
    "IP": "지식재산권",
    "LABOR_EMPLOYMENT": "노동 / 고용",
    "MA_CORP_ANTITRUST": "M&A / 독점금지",
    "PLATFORM_PUBLISHING": "플랫폼 / 유통",
    "PRIVACY_SECURITY": "개인정보 / 보안",
    "ETC": "기타",
}

CATEGORY_SHORT_LABELS = {
    "IP": "IP",
    "MA_CORP_ANTITRUST": "M&A",
    "PRIVACY_SECURITY": "개인정보",
    "CONSUMER_MONETIZATION": "과금",
    "CONTENT_AGE": "연령",
    "PLATFORM_PUBLISHING": "플랫폼",
    "AI_EMERGING": "AI",
    "ESPORTS_MARKETING": "e스포츠",
    "LABOR_EMPLOYMENT": "노동",
    "ETC": "기타",
}

CIRCLED_NUMERALS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def compute_category_counts(nodes: list[BriefingNode]) -> list[tuple[str, int]]:
    """Compute stable, display-ready category counts for the header breadcrumb."""
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.category] = counts.get(node.category, 0) + 1

    ordered = [
        (CATEGORY_SHORT_LABELS.get(category, category), counts[category])
        for category in CATEGORY_ORDER
        if counts.get(category)
    ]
    extra_categories = sorted(category for category in counts if category not in CATEGORY_ORDER)
    ordered.extend(
        (CATEGORY_SHORT_LABELS.get(category, category), counts[category])
        for category in extra_categories
    )
    return ordered


def render_email(
    nodes: list[BriefingNode],
    date: str,
    template_dir: str = "templates",
    web_url: str = "https://lowtidebuild.github.io/game-legal-briefing/",
) -> str:
    """Render the HTML email body for a briefing."""
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("email/briefing.html")
    html = template.render(
        nodes=nodes,
        date=date,
        cat_labels=CATEGORY_LABELS,
        cat_counts=compute_category_counts(nodes),
        circled=CIRCLED_NUMERALS,
        web_url=web_url,
    )

    try:  # pragma: no cover - depends on optional package availability
        from premailer import transform

        return transform(html, strip_important=False)
    except ImportError:
        return html


def write_email_preview(html_body: str, output_dir: str = "output") -> str:
    """Write a local email preview artifact without sending anything."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "email-preview.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html_body)
    return path
