"""
Account views: register, login, logout.

Design reference:
- API.md §3 (accounts)
- AUTHZ.md §1 (actor resolution)
- UX.md §1 (screen inventory)
"""

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from services import accounts as accounts_service


def _get_cookie_secure():
    return getattr(settings, "RUBRIC_COOKIE_SECURE", False)


def _sanitize_next_url(request, next_url, default="/projects"):
    if not next_url:
        return default
    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    User registration view (/accounts/register).
    GET: renders registration form.
    POST: creates user, creates session token, sets session cookie.
    """
    if request.method == "POST":
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")
        display_name = request.POST.get("display_name", "")

        try:
            user, raw_token = accounts_service.register(
                email=email,
                password=password,
                display_name=display_name,
            )
            raw_next = request.POST.get("next") or request.GET.get("next")
            next_url = _sanitize_next_url(request, raw_next, default="/projects")
            response = HttpResponseRedirect(next_url)
            response.set_cookie(
                "session",
                raw_token,
                httponly=True,
                samesite="Lax",
                secure=_get_cookie_secure(),
            )
            return response
        except ValueError as exc:
            context = {
                "error": str(exc),
                "email": email,
                "display_name": display_name,
            }
            return render(request, "accounts/register.html", context, status=400)

    return render(request, "accounts/register.html")


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    User login view (/login, /accounts/login).
    GET: renders login form.
    POST: validates credentials, sets session cookie.
    Failure must not reveal whether an email exists.
    """
    if request.method == "POST":
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")

        try:
            user, raw_token = accounts_service.login(email=email, password=password)
            raw_next = request.POST.get("next") or request.GET.get("next")
            if raw_next:
                next_url = _sanitize_next_url(request, raw_next, default="/projects")
            else:
                if user.is_site_admin or user.event_memberships.filter(role="ORGANIZER").exists():
                    next_url = "/organizer"
                else:
                    next_url = "/projects"

            response = HttpResponseRedirect(next_url)
            response.set_cookie(
                "session",
                raw_token,
                httponly=True,
                samesite="Lax",
                secure=_get_cookie_secure(),
            )
            return response
        except ValueError:
            context = {
                "error": accounts_service.GENERIC_LOGIN_ERROR,
                "email": email,
            }
            # Indistinguishable error response for unknown email and wrong password
            return render(request, "accounts/login.html", context, status=401)

    return render(request, "accounts/login.html")


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """
    User logout view (/logout, /accounts/logout).
    Invalidates token server-side and clears session cookie.
    """
    raw_token = request.COOKIES.get("session")
    if raw_token:
        accounts_service.logout(raw_token)

    response = HttpResponseRedirect("/login")
    response.delete_cookie("session", samesite="Lax")
    return response
