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
from django.views.decorators.http import require_http_methods

from services import accounts as accounts_service


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
            next_url = request.POST.get("next") or request.GET.get("next") or "/projects"
            response = HttpResponseRedirect(next_url)
            response.set_cookie(
                "session",
                raw_token,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
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
            next_url = request.POST.get("next") or request.GET.get("next")
            if not next_url:
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
                secure=not settings.DEBUG,
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
