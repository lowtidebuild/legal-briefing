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
    assert "repair_date" in delivery_block


def test_generation_command_explicitly_disables_delivery():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "briefing.yml").read_text(
        encoding="utf-8"
    )
    assert "python main.py --delivery none" in workflow


def test_web_repair_preserves_existing_data_and_is_excluded_from_delivery():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "briefing.yml").read_text(
        encoding="utf-8"
    )
    assert "python main.py --delivery none --output /tmp/briefing-repair" in workflow
    assert "python scripts/merge_daily_for_web.py" in workflow
    delivery_position = workflow.index("name: Deliver generated run")
    delivery_condition = workflow[delivery_position:].split("run: |", 1)[0]
    assert "inputs.repair_date == '' || inputs.repair_date == null" in delivery_condition
