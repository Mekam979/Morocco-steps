"""
Admin Blueprint — step 1: auth + base template only.

Routes:
    GET/POST /admin/login
    GET      /admin/logout
    GET      /admin/dashboard   (placeholder)
"""

import os
import secrets
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for, session
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("admin.dashboard"))

    error = None
    if request.method == "POST":
        submitted = request.form.get("password", "")
        expected = os.getenv("ADMIN_PASSWORD", "")
        if expected and secrets.compare_digest(submitted, expected):
            session["admin"] = True
            return redirect(url_for("admin.dashboard"))
        error = "Mot de passe incorrect."

    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")
