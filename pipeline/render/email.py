from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline.models import BriefingNode


def render_email(
    nodes: list[BriefingNode],
    date: str,
    template_dir: str = "templates",
) -> str:
    """Render the HTML email body for a briefing."""
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("email/briefing.html")
    html = template.render(nodes=nodes, date=date)

    try:  # pragma: no cover - depends on optional package availability
        from premailer import transform

        return transform(html)
    except ImportError:
        return html

