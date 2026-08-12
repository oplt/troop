from backend.modules.orchestration.router import router
from backend.modules.orchestration.workflow_templates import BUILTIN_WORKFLOW_TEMPLATES


def test_workflow_template_catalog_uses_supported_execution_defaults():
    supported_modes = {"assisted", "semi-autonomous", "autonomous"}
    supported_routing = {
        "capability_based",
        "priority_sla",
        "sla_priority",
        "cost_aware",
        "model_availability",
        "user_pinned",
        "throughput",
    }

    assert BUILTIN_WORKFLOW_TEMPLATES
    for template in BUILTIN_WORKFLOW_TEMPLATES:
        execution = template["suggested_execution"]
        assert execution["autonomy_level"] in supported_modes
        assert execution["routing_mode"] in supported_routing


def test_workflow_template_apply_route_is_registered():
    from fastapi.routing import APIRoute

    route = next(
        item
        for item in router.routes
        if isinstance(item, APIRoute)
        and item.path == "/projects/{project_id}/workflow-templates/{template_id}/apply"
    )

    assert "POST" in route.methods
