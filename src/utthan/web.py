from __future__ import annotations

import csv
import hmac
import io
import os
import re
import secrets
import sqlite3
import string
import tempfile
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from .database import Database, from_paise, reset_audit_actor, set_audit_actor
from .reports import (
    MONTHS,
    export_period_csv,
    generate_all_bills,
    generate_due_list,
    generate_member_bill,
    generate_receipt,
)

View = TypeVar("View", bound=Callable[..., Any])
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,50}$")
LOGIN_TEMPLATE = "login.html"
CREDENTIALS_TEMPLATE = "credentials.html"
LOCAL_ADDRESSES = {"127.0.0.1", "::1", "localhost"}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _secret_key(data_dir: Path) -> str:
    configured = os.environ.get("UTTHAN_SECRET_KEY")
    if configured:
        return configured
    target = data_dir / ".web-secret"
    if target.exists():
        return target.read_text(encoding="utf-8").strip()
    value = secrets.token_hex(32)
    target.write_text(value, encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return value


def _password_error(password: str) -> str | None:
    if len(password) < 10:
        return "Password must contain at least 10 characters."
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password):
        return "Password must contain uppercase and lowercase letters."
    if not re.search(r"\d", password):
        return "Password must contain a number."
    return None


def _username(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError("Username must be 3-50 letters, numbers, dots, dashes or underscores.")
    return value


def _amount(value: str, label: str = "Amount") -> float:
    try:
        result = float(value.replace(",", "").strip() or "0")
    except ValueError as exc:
        raise ValueError(f"{label} must be a number") from exc
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _temporary_password() -> str:
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    required.extend(secrets.choice(alphabet) for _ in range(12))
    return "".join(required)


def _date(value: str, label: str = "Date") -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD") from exc


# Route registration is intentionally co-located so every endpoint shares the same database
# instance and security hooks. Individual handlers remain small and independently tested.
def create_app(data_dir: Path | None = None, test_config: dict[str, Any] | None = None) -> Flask:  # NOSONAR
    # CSRF is enforced for every state-changing request in load_identity() below.
    app = Flask(__name__)  # NOSONAR
    db = Database(data_dir)
    app.config.from_mapping(
        SECRET_KEY=_secret_key(db.data_dir),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_flag("UTTHAN_COOKIE_SECURE"),
        MAX_CONTENT_LENGTH=64 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    trusted_proxies = int(os.environ.get("UTTHAN_TRUSTED_PROXIES", "0") or 0)
    if trusted_proxies > 0:
        # Behind Nginx/IIS/Caddy: use the forwarded client IP and HTTPS scheme.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=trusted_proxies, x_proto=trusted_proxies, x_host=trusted_proxies
        )
    app.extensions["utthan_db"] = db

    def csrf_token() -> str:
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return str(token)

    def current_db() -> Database:
        return app.extensions["utthan_db"]

    def client_details() -> tuple[str, str]:
        return (request.remote_addr or "unknown", request.user_agent.string or "")

    def issue_member_login(member: Any) -> dict[str, str]:
        base = f"member{member['member_no']}"
        username, suffix = base, 1
        while current_db().user_by_username(username) is not None:
            suffix += 1
            username = f"{base}-{suffix}"
        password = _temporary_password()
        current_db().create_user(
            username, generate_password_hash(password), "member", member["id"],
            must_change_password=True,
        )
        return {
            "member_no": str(member["member_no"]), "name": member["name"],
            "username": username, "password": password,
        }

    def show_credentials(slips: list[dict[str, str]], title: str) -> str:
        return render_template(
            CREDENTIALS_TEMPLATE, slips=slips, title=title, login_url=url_for("login", _external=True),
        )

    def run_auto_backup() -> None:
        try:
            current_db().auto_backup()
        except (OSError, sqlite3.Error):
            app.logger.exception("Automatic backup failed")

    @app.before_request
    def load_identity() -> Response | None:
        user_id = session.get("user_id")
        g.user = current_db().user(int(user_id)) if user_id else None
        if g.user is not None and not g.user["is_active"]:
            session.clear()
            g.user = None
        g.audit_token = set_audit_actor(g.user["id"] if g.user else None)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            submitted = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(str(submitted), str(expected)):
                abort(400, "The form expired. Refresh the page and try again.")
        allowed = {"change_password", "logout", "static"}
        if g.user is not None and g.user["must_change_password"] and request.endpoint not in allowed:
            return redirect(url_for("change_password"))
        return None

    @app.teardown_request
    def clear_identity(_: BaseException | None) -> None:
        token = getattr(g, "audit_token", None)
        if token is not None:
            reset_audit_actor(token)

    @app.after_request
    def security_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if g.get("user") is not None:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def template_context() -> dict[str, Any]:
        return {
            "csrf_token": csrf_token,
            "current_user": getattr(g, "user", None),
            "society_name": current_db().setting("society_name", "UTHAN CREATIVE SOCIETY"),
            "months": MONTHS,
            "today": date.today().isoformat(),
        }

    @app.template_filter("money")
    def money(value: int | None) -> str:
        return f"₹{from_paise(value):,.2f}"

    @app.template_filter("when")
    def when(value: str | None) -> str:
        if not value:
            return "Never"
        try:
            moment = datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            return value
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone().strftime("%d %b %Y, %I:%M %p")

    def login_required(view: View) -> View:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if g.user is None:
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    def admin_required(view: View) -> View:
        @wraps(view)
        @login_required
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if g.user["role"] != "admin":
                abort(403)
            return view(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    @app.get("/")
    def index() -> Response:
        if current_db().account_count() == 0:
            return redirect(url_for("setup"))
        if g.user is None:
            return redirect(url_for("login"))
        return redirect(url_for("admin_dashboard" if g.user["role"] == "admin" else "portal"))

    @app.route("/setup", methods=["GET", "POST"])
    def setup() -> str | Response:
        if current_db().account_count() != 0:
            return redirect(url_for("index"))
        setup_token = os.environ.get("UTTHAN_SETUP_TOKEN", "")
        # Requests relayed by a reverse proxy are never treated as local, even from 127.0.0.1.
        proxied = "X-Forwarded-For" in request.headers or "Forwarded" in request.headers
        if not setup_token and (proxied or request.remote_addr not in LOCAL_ADDRESSES):
            abort(403, "First-time setup is only allowed from the server itself unless "
                       "UTTHAN_SETUP_TOKEN is configured.")
        if request.method == "POST":
            try:
                if setup_token and not hmac.compare_digest(
                    request.form.get("setup_token", ""), setup_token
                ):
                    raise ValueError("Setup code is incorrect.")
                username = _username(request.form.get("username", ""))
                password = request.form.get("password", "")
                if error := _password_error(password):
                    raise ValueError(error)
                if password != request.form.get("confirm_password", ""):
                    raise ValueError("Passwords do not match.")
                current_db().create_user(
                    username,
                    generate_password_hash(password),
                    "admin",
                    must_change_password=False,
                )
                flash("Administrator account created. Sign in to continue.", "success")
                return redirect(url_for("login"))
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template("setup.html", setup_token_required=bool(setup_token))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str | Response | tuple[str, int]:
        if current_db().account_count() == 0:
            return redirect(url_for("setup"))
        if g.user is not None:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            ip_address, user_agent = client_details()
            identifier = f"{username}|{ip_address}"
            remaining = current_db().login_lock_seconds(identifier)
            if remaining:
                flash("Too many attempts. Try again in about 15 minutes.", "error")
                return render_template(LOGIN_TEMPLATE), 429
            user = current_db().user_by_username(username)
            valid = bool(user and user["is_active"] and check_password_hash(user["password_hash"], password))
            if not valid:
                current_db().record_login_failure(identifier)
                current_db().record_auth_event(username, "LOGIN_FAILED", ip_address, user_agent)
                flash("Invalid username or password.", "error")
                return render_template(LOGIN_TEMPLATE), 401
            current_db().clear_login_failures(identifier)
            current_db().touch_user_login(user["id"])
            current_db().record_auth_event(username, "LOGIN_SUCCESS", ip_address, user_agent)
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            session.permanent = True
            return redirect(url_for("index"))
        return render_template(LOGIN_TEMPLATE)

    @app.post("/logout")
    @login_required
    def logout() -> Response:
        ip_address, user_agent = client_details()
        current_db().record_auth_event(g.user["username"], "LOGOUT", ip_address, user_agent)
        session.clear()
        return redirect(url_for("login"))

    @app.route("/password", methods=["GET", "POST"])
    @login_required
    def change_password() -> str | Response:
        if request.method == "POST":
            current = request.form.get("current_password", "")
            password = request.form.get("password", "")
            try:
                if not check_password_hash(g.user["password_hash"], current):
                    raise ValueError("Current password is incorrect.")
                if error := _password_error(password):
                    raise ValueError(error)
                if password != request.form.get("confirm_password", ""):
                    raise ValueError("Passwords do not match.")
                current_db().update_user_password(g.user["id"], generate_password_hash(password))
                flash("Password changed successfully.", "success")
                return redirect(url_for("index"))
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template("change_password.html")

    @app.get("/portal")
    @login_required
    def portal() -> str | Response:
        if g.user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        member = current_db().member(g.user["member_id"])
        if member is None:
            abort(404)
        dues = current_db().member_dues(member["id"])
        loans = current_db().member_loans(member["id"])
        transactions = current_db().member_transactions(member["id"])
        total_due = sum(max(0, row["total_due_paise"] - row["total_paid_paise"]) for row in dues)
        return render_template(
            "portal.html",
            member=member,
            dues=dues,
            loans=loans,
            transactions=transactions,
            total_due=total_due,
        )

    def authorize_due(due_id: int) -> Any:
        due = current_db().due(due_id)
        if due is None:
            abort(404)
        if g.user["role"] != "admin" and due["member_id"] != g.user["member_id"]:
            abort(403)
        return due

    @app.get("/bill/<int:due_id>")
    @login_required
    def bill(due_id: int) -> Response:
        authorize_due(due_id)
        path = generate_member_bill(current_db(), due_id)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/receipt/<int:transaction_id>")
    @login_required
    def receipt(transaction_id: int) -> Response:
        transaction = current_db().transaction(transaction_id)
        if transaction is None or transaction["due_id"] is None:
            abort(404)
        if g.user["role"] != "admin" and transaction["member_id"] != g.user["member_id"]:
            abort(403)
        path = generate_receipt(current_db(), transaction_id)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/admin")
    @admin_required
    def admin_dashboard() -> str:
        run_auto_backup()
        return render_template(
            "admin_dashboard.html",
            stats=current_db().dashboard(),
            transactions=current_db().transactions(limit=12),
            login_count=sum(1 for row in current_db().list_users() if row["role"] == "member"),
        )

    @app.route("/admin/members", methods=["GET", "POST"])
    @admin_required
    def members() -> str | Response:
        if request.method == "POST":
            try:
                current_db().add_member(
                    request.form.get("name", ""),
                    request.form.get("phone", ""),
                    request.form.get("address", ""),
                    request.form.get("nominee", ""),
                    _date(request.form.get("join_date", ""), "Join date"),
                    _amount(request.form.get("opening_contribution", "0"), "Opening savings"),
                    request.form.get("notes", ""),
                )
                flash("Member added. Use Generate login to give them portal access.", "success")
                return redirect(url_for("members"))
            except ValueError as exc:
                flash(str(exc), "error")
        query = request.args.get("q", "").strip().lower()
        member_rows = current_db().list_members(include_inactive=True)
        if query:
            member_rows = [
                row
                for row in member_rows
                if query in row["name"].lower()
                or query in row["phone"].lower()
                or query == str(row["member_no"])
            ]
        accounts = {
            row["member_id"]: row for row in current_db().list_users() if row["member_id"]
        }
        return render_template(
            "members.html", members=member_rows, query=query, accounts=accounts,
        )

    @app.post("/admin/members/<int:member_id>/login")
    @admin_required
    def generate_member_login(member_id: int) -> str | Response:
        member = current_db().member(member_id)
        if member is None:
            abort(404)
        if current_db().user_for_member(member_id) is not None:
            flash("This member already has a login. Use Reset password instead.", "error")
            return redirect(url_for("users"))
        return show_credentials([issue_member_login(member)], "Member login created")

    @app.get("/admin/members/<int:member_id>")
    @admin_required
    def member_history(member_id: int) -> str:
        member = current_db().member(member_id)
        if member is None:
            abort(404)
        member_dues = current_db().member_dues(member_id)
        return render_template(
            "member_history.html",
            member=member,
            account=current_db().user_for_member(member_id),
            dues=member_dues,
            loans=current_db().member_loans(member_id),
            transactions=current_db().member_transactions(member_id),
            total_due=sum(
                max(0, row["total_due_paise"] - row["total_paid_paise"])
                for row in member_dues
            ),
        )

    @app.post("/admin/members/<int:member_id>/status")
    @admin_required
    def member_status(member_id: int) -> Response:
        member = current_db().member(member_id)
        if member is None:
            abort(404)
        current_db().update_member_status(
            member_id, "Inactive" if member["status"] == "Active" else "Active"
        )
        flash("Member status updated.", "success")
        return redirect(url_for("members"))

    @app.route("/admin/users", methods=["GET", "POST"])
    @admin_required
    def users() -> str | Response:
        if request.method == "POST":
            try:
                role = request.form.get("role", "member")
                if role == "member":
                    member = current_db().member(int(request.form.get("member_id") or 0))
                    if member is None:
                        raise ValueError("Select the member who needs a login.")
                    if current_db().user_for_member(member["id"]) is not None:
                        raise ValueError("This member already has a login.")
                    return show_credentials([issue_member_login(member)], "Member login created")
                if role != "admin":
                    raise ValueError("Invalid account role")
                username = _username(request.form.get("username", ""))
                password = _temporary_password()
                current_db().create_user(
                    username, generate_password_hash(password), "admin", must_change_password=True,
                )
                return show_credentials(
                    [{"member_no": "-", "name": "Administrator", "username": username,
                      "password": password}],
                    "Administrator login created",
                )
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template(
            "users.html",
            users=current_db().list_users(),
            available_members=current_db().members_without_users(),
        )

    @app.post("/admin/users/provision")
    @admin_required
    def provision_users() -> str | Response:
        slips = [issue_member_login(member) for member in current_db().members_without_users()]
        if not slips:
            flash("Every active member already has a login.", "success")
            return redirect(url_for("users"))
        if request.form.get("output") != "csv":
            return show_credentials(slips, f"{len(slips)} member logins created")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Member No", "Member Name", "Username", "Temporary Password"])
        writer.writerows(
            [slip["member_no"], slip["name"], slip["username"], slip["password"]] for slip in slips
        )
        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=member-login-credentials.csv"},
        )

    @app.post("/admin/users/<int:user_id>/reset")
    @admin_required
    def reset_user_password(user_id: int) -> str | Response:
        target = current_db().user(user_id)
        if target is None:
            abort(404)
        if target["id"] == g.user["id"]:
            flash("Use Change password for your own account.", "error")
            return redirect(url_for("users"))
        password = _temporary_password()
        current_db().update_user_password(
            user_id, generate_password_hash(password), must_change_password=True
        )
        return show_credentials(
            [{"member_no": str(target["member_no"] or "-"),
              "name": target["member_name"] or "Administrator",
              "username": target["username"], "password": password}],
            "Password reset",
        )

    @app.post("/admin/users/<int:user_id>/status")
    @admin_required
    def user_status(user_id: int) -> Response:
        target = current_db().user(user_id)
        if target is None:
            abort(404)
        if target["id"] == g.user["id"]:
            flash("You cannot deactivate your own account.", "error")
        elif target["role"] == "admin" and target["is_active"] and current_db().active_admin_count() <= 1:
            flash("At least one active administrator is required.", "error")
        else:
            current_db().update_user_active(user_id, not bool(target["is_active"]))
            flash("Account status updated.", "success")
        return redirect(url_for("users"))

    @app.route("/admin/loans", methods=["GET", "POST"])
    @admin_required
    def loans() -> str | Response:
        if request.method == "POST":
            try:
                current_db().issue_loan(
                    int(request.form["member_id"]),
                    _amount(request.form.get("amount", "0")),
                    _date(request.form.get("issue_date", ""), "Issue date"),
                    request.form.get("loan_type", "Fresh"),
                    _amount(request.form.get("emi", "0"), "EMI"),
                    _amount(request.form.get("interest_rate", "0"), "Interest rate"),
                    request.form.get("notes", ""),
                )
                flash("Loan issued successfully.", "success")
                return redirect(url_for("loans"))
            except (KeyError, ValueError) as exc:
                flash(str(exc), "error")
        return render_template(
            "loans.html",
            loans=current_db().list_loans(),
            members=current_db().list_members(),
            default_emi=from_paise(int(current_db().setting("default_emi", "100000"))),
            default_rate=int(current_db().setting("monthly_interest_bp", "150")) / 100,
        )

    @app.get("/admin/dues")
    @admin_required
    def dues() -> str:
        periods = current_db().list_periods()
        selected_id = request.args.get("period_id", type=int)
        if selected_id is None and periods:
            selected_id = periods[0]["id"]
        selected = next((row for row in periods if row["id"] == selected_id), None)
        due_rows = current_db().period_dues(selected_id) if selected else []
        query = request.args.get("q", "").strip().lower()
        if query:
            due_rows = [
                row
                for row in due_rows
                if query in row["name"].lower() or query == str(row["member_no"])
            ]
        receipt_id = request.args.get("receipt", type=int)
        receipt_info = current_db().receipt_details(receipt_id) if receipt_id else None
        return render_template(
            "dues.html",
            periods=periods,
            selected=selected,
            dues=due_rows,
            query=query,
            receipt_info=receipt_info,
        )

    @app.post("/admin/dues/generate")
    @admin_required
    def generate_period() -> Response:
        periods = current_db().list_periods()
        if periods:
            year, month = periods[0]["year"], periods[0]["month"]
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        else:
            year, month = date.today().year, date.today().month
        period_id = current_db().generate_period(year, month)
        flash(f"Dues generated for {MONTHS[month - 1]} {year}.", "success")
        return redirect(url_for("dues", period_id=period_id))

    @app.route("/admin/dues/<int:due_id>/payment", methods=["GET", "POST"])
    @admin_required
    def payment(due_id: int) -> str | Response:
        due = authorize_due(due_id)
        if request.method == "POST":
            try:
                transaction_id = current_db().record_payment(
                    due_id,
                    _amount(request.form.get("contribution", "0"), "Contribution"),
                    _amount(request.form.get("principal", "0"), "Principal"),
                    _amount(request.form.get("interest", "0"), "Interest"),
                    _amount(request.form.get("arrears", "0"), "Previous due"),
                    _amount(request.form.get("late_fee", "0"), "Late fee"),
                    _date(request.form.get("payment_date", ""), "Payment date"),
                    request.form.get("payment_method", "Cash"),
                    request.form.get("reference", ""),
                    request.form.get("notes", ""),
                )
                flash(f"Payment saved. Receipt UT-{transaction_id:06d} is ready.", "success")
                return redirect(url_for("dues", period_id=due["period_id"], receipt=transaction_id))
            except ValueError as exc:
                flash(str(exc), "error")
        outstanding = {
            "contribution": max(0, due["contribution_due_paise"] - due["contribution_paid_paise"]),
            "principal": max(0, due["emi_due_paise"] - due["principal_paid_paise"]),
            "interest": max(0, due["interest_due_paise"] - due["interest_paid_paise"]),
            "arrears": max(0, due["arrears_due_paise"] - due["arrears_paid_paise"]),
            "late_fee": max(0, due["late_fee_paise"] - due["late_fee_paid_paise"]),
        }
        return render_template("payment.html", due=due, outstanding=outstanding)

    @app.post("/admin/periods/<int:period_id>/close")
    @admin_required
    def close_period(period_id: int) -> Response:
        if not any(row["id"] == period_id for row in current_db().list_periods()):
            abort(404)
        try:
            current_db().backup()
        except (OSError, sqlite3.Error):
            flash("Safety backup failed, so the period was not closed. Try again.", "error")
            return redirect(url_for("dues", period_id=period_id))
        current_db().close_period(period_id)
        flash("Safety backup created and period closed. It can no longer accept payments.", "success")
        return redirect(url_for("dues", period_id=period_id))

    @app.route("/admin/cashbook", methods=["GET", "POST"])
    @admin_required
    def cashbook() -> str | Response:
        if request.method == "POST":
            try:
                current_db().add_expense(
                    _date(request.form.get("expense_date", ""), "Expense date"),
                    request.form.get("category", ""),
                    _amount(request.form.get("amount", "0")),
                    request.form.get("notes", ""),
                )
                flash("Expense added.", "success")
                return redirect(url_for("cashbook"))
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template(
            "cashbook.html",
            transactions=current_db().transactions(),
            expenses=current_db().list_expenses(),
        )

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def settings() -> str | Response:
        if request.method == "POST":
            try:
                current_db().save_settings(
                    {
                        "society_name": request.form.get("society_name", "").strip(),
                        "group_name": request.form.get("group_name", "").strip(),
                        "monthly_contribution": str(
                            round(_amount(request.form.get("monthly_contribution", "0")) * 100)
                        ),
                        "default_emi": str(round(_amount(request.form.get("default_emi", "0")) * 100)),
                        "monthly_interest_bp": str(
                            round(_amount(request.form.get("monthly_interest_rate", "0")) * 100)
                        ),
                    }
                )
                flash("Settings saved.", "success")
                return redirect(url_for("settings"))
            except ValueError as exc:
                flash(str(exc), "error")
        values = {
            "society_name": current_db().setting("society_name"),
            "group_name": current_db().setting("group_name"),
            "monthly_contribution": from_paise(
                int(current_db().setting("monthly_contribution", "50000"))
            ),
            "default_emi": from_paise(int(current_db().setting("default_emi", "100000"))),
            "monthly_interest_rate": int(current_db().setting("monthly_interest_bp", "150")) / 100,
        }
        return render_template("settings.html", values=values)

    @app.get("/admin/reports")
    @admin_required
    def reports_page() -> str:
        latest = current_db().latest_auto_backup()
        return render_template(
            "reports.html",
            periods=current_db().list_periods(),
            latest_auto_backup=(
                datetime.fromtimestamp(latest.stat().st_mtime).strftime("%d %b %Y, %I:%M %p")
                if latest else None
            ),
        )

    @app.get("/admin/reports/due-list/<int:period_id>.pdf")
    @admin_required
    def due_list_report(period_id: int) -> Response:
        path = generate_due_list(current_db(), period_id)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/admin/reports/all-bills/<int:period_id>.pdf")
    @admin_required
    def all_bills_report(period_id: int) -> Response:
        try:
            path = generate_all_bills(current_db(), period_id)
        except ValueError as exc:
            flash(str(exc), "success")
            return redirect(url_for("dues", period_id=period_id))
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get("/admin/reports/due-list/<int:period_id>.csv")
    @admin_required
    def due_list_csv(period_id: int) -> Response:
        path = export_period_csv(current_db(), period_id)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.post("/admin/backup")
    @admin_required
    def backup() -> Response:
        path = current_db().backup()
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.post("/admin/restore")
    @admin_required
    def restore_backup() -> Response:
        uploaded = request.files.get("backup_file")
        if uploaded is None or not uploaded.filename:
            flash("Choose a web portal backup file to restore.", "error")
            return redirect(url_for("reports_page"))
        try:
            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "uploaded-backup.db"
                uploaded.save(source)
                current_db().validate_web_backup(source)
                current_db().restore(source)
            ip_address, user_agent = client_details()
            current_db().record_auth_event(
                g.user["username"], "BACKUP_RESTORED", ip_address, user_agent
            )
            session.clear()
            flash("Backup restored. Sign in using an administrator account from that backup.", "success")
            return redirect(url_for("login"))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("reports_page"))

    @app.get("/admin/activity")
    @admin_required
    def activity() -> str:
        return render_template(
            "activity.html",
            audit_entries=current_db().audit_entries(),
            auth_events=current_db().auth_event_entries(),
        )

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def friendly_error(error: Any) -> tuple[str, int]:
        return render_template("error.html", error=error), int(error.code)

    return app
