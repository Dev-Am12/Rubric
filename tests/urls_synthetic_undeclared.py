"""
Synthetic URLconf containing an intentionally undeclared route.
Used by ControlCaseUndeclaredRouteTest to prove that AuthzCoverageTest
fails when an endpoint is added without an authz declaration.
"""

from django.http import HttpResponse
from django.urls import path

urlpatterns = [
    path(
        'synthetic-undeclared-control-route',
        lambda request: HttpResponse('control'),
        name='synthetic_control_case_undeclared',
    ),
]
