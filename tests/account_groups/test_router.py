from fastapi.routing import APIRoute

from app.account_groups.router import router


def test_member_mutation_routes_document_missing_member_as_not_found():
    path = "/account-groups/{group_id}/members/{user_id}"
    member_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and (route.methods or set()) & {"PATCH", "DELETE"}
    ]

    assert len(member_routes) == 2
    assert all(404 in route.responses for route in member_routes)
