from pathlib import Path


def test_pages_deploy_precedes_external_delivery_and_gates_it():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "briefing.yml").read_text(
        encoding="utf-8"
    )
    deploy_position = workflow.index("name: Deploy to GitHub Pages")
    record_position = workflow.index("name: Record successful Pages deployment")
    delivery_position = workflow.index("name: Deliver generated run")
    assert deploy_position < record_position < delivery_position
    delivery_block = workflow[delivery_position:]
    assert "success()" in delivery_block
    assert "web_only" in delivery_block
    assert "render_date" in delivery_block


def test_generation_command_explicitly_disables_delivery():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "briefing.yml").read_text(
        encoding="utf-8"
    )
    assert "python main.py --delivery none" in workflow
