"""Moving schemas must not rename published OpenAPI components."""

import pytest

from app.main import app


@pytest.mark.parametrize(
    ("path", "component"),
    [
        ("/api/tasks/{task_id}/move", "app__schemas__MoveIn"),
        ("/api/volumes/{volume_id}/move", "app__routers__volumes__MoveIn"),
    ],
)
def test_move_requests_keep_their_published_component_names(path, component):
    contract = app.openapi()
    body = contract["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": f"#/components/schemas/{component}"}
    assert component in contract["components"]["schemas"]
