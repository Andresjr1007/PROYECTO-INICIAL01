from __future__ import annotations

import sys
import secrets
import tempfile
from datetime import datetime
from functools import wraps
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = PROJECT_DIR / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

from database import (
    ALLOWED_PRIORITIES,
    ALLOWED_STATUSES,
    BASE_DIR,
    DB_PATH,
    DEFAULT_CATEGORIES,
    ROLE_LABELS,
    STATUS_BADGES,
    STATUS_LABELS,
    STATUS_TRANSITIONS,
    UPLOAD_DIR,
    add_attachment,
    add_response,
    assign_ticket,
    authenticate_user,
    claim_ticket,
    close_ticket,
    create_category,
    create_ticket,
    create_user,
    dashboard_metrics,
    get_category,
    get_category_by_name,
    get_ticket,
    get_ticket_attachments,
    get_ticket_history,
    get_ticket_responses,
    get_user,
    get_user_by_email,
    init_db,
    list_categories,
    list_employees,
    list_tickets,
    list_users,
    month_label_es,
    monthly_report,
    register_client,
    remove_category,
    remove_user,
    seed_demo_data,
    set_ticket_feedback,
    ticket_average_resolution_hours,
    toggle_user_status,
    update_category,
    update_ticket_status,
    update_user,
)
from reports import generate_excel_report, generate_pdf_report


app = Flask(__name__)
app.config["SECRET_KEY"] = "portal-atencion-clientes-dev-secret"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True

PROJECT_CREATOR = "Andres Felipe Figueroa"
EXPORT_DIR = BASE_DIR / "data" / "exports"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "csv", "doc", "docx", "xls", "xlsx"}


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_user(int(user_id))
    if not user or user["status"] != "active":
        session.pop("user_id", None)
        return None
    return user


def login_user(user):
    session["user_id"] = user["id"]


def logout_user():
    session.clear()


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_field() -> Markup:
    return Markup(f'<input type="hidden" name="csrf_token" value="{escape(csrf_token())}">')


def validate_csrf() -> None:
    if request.method != "POST":
        return
    token = session.get("_csrf_token")
    form_token = request.form.get("csrf_token")
    if not token or not form_token or token != form_token:
        abort(400, description="Token CSRF inválido.")


@app.before_request
def load_user_and_protect_forms():
    g.user = get_current_user()
    if request.method == "POST":
        validate_csrf()


@app.context_processor
def inject_helpers():
    return {
        "current_user": g.get("user"),
        "project_creator": PROJECT_CREATOR,
        "csrf_field": csrf_field,
        "role_label": role_label,
        "status_label": status_label,
        "status_badge": status_badge,
        "priority_label": priority_label,
        "format_datetime": format_datetime,
        "human_duration": human_duration,
        "month_label_es": month_label_es,
        "status_options": list(STATUS_LABELS.items()),
        "priority_options": list(ALLOWED_PRIORITIES),
        "role_options": list(ROLE_LABELS.items()),
        "year_now": datetime.now().year,
    }


def role_label(value: str | None) -> str:
    return ROLE_LABELS.get(value or "", value or "-")


def status_label(value: str | None) -> str:
    return STATUS_LABELS.get(value or "", value or "-")


def status_badge(value: str | None) -> str:
    return STATUS_BADGES.get(value or "", "status-neutral")


def priority_label(value: str | None) -> str:
    return {
        "low": "Baja",
        "medium": "Media",
        "high": "Alta",
        "urgent": "Crítica",
    }.get(value or "", value or "-")


def format_datetime(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def human_duration(start: str | None, end: str | None = None) -> str:
    if not start:
        return "-"
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end) if end else datetime.now()
    except ValueError:
        return "-"
    delta = end_dt - start_dt
    total_hours = max(delta.total_seconds() / 3600, 0)
    if total_hours < 1:
        minutes = int(delta.total_seconds() // 60)
        return f"{minutes} min"
    if total_hours < 24:
        return f"{total_hours:.1f} h"
    days = int(total_hours // 24)
    remaining_hours = int(total_hours % 24)
    return f"{days} d {remaining_hours} h"


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            flash("Debes iniciar sesión para continuar.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = g.get("user")
        if not user:
            flash("Debes iniciar sesión para continuar.", "warning")
            return redirect(url_for("login"))
        if user["role_slug"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def can_view_ticket(user, ticket) -> bool:
    if not user or not ticket:
        return False
    if user["role_slug"] != "client":
        return True
    return ticket["client_id"] == user["id"]


def can_edit_ticket(user, ticket) -> bool:
    if not user or not ticket:
        return False
    if user["role_slug"] == "admin":
        return True
    if user["role_slug"] == "employee":
        return True
    return ticket["client_id"] == user["id"]


def allowed_extensions(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploads(ticket, files, author_id: int) -> tuple[int, int]:
    saved = 0
    skipped = 0
    ticket_dir = UPLOAD_DIR / ticket["code"]
    ticket_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_extensions(file.filename):
            skipped += 1
            continue
        safe_name = secure_filename(file.filename)
        unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        file_path = ticket_dir / unique_name
        file.save(file_path)
        add_attachment(ticket["id"], author_id, file.filename, unique_name, file.mimetype)
        saved += 1
    return saved, skipped


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def ticket_status_choices(ticket) -> list[tuple[str, str]]:
    current = ticket["status"]
    allowed = STATUS_TRANSITIONS.get(current, set())
    return [(status, STATUS_LABELS[status]) for status in allowed]


def open_data_year_month() -> tuple[int, int]:
    now = datetime.now()
    return now.year, now.month


@app.route("/")
def index():
    if g.get("user"):
        return redirect(url_for("dashboard"))
    demo_emails = {
        "admin@portal.local",
        "agente@portal.local",
        "cliente@portal.local",
        "cliente2@portal.local",
    }
    return render_template(
        "landing.html",
        demo_accounts=[
            account
            for account in list_users(include_inactive=False)
            if account["email"] in demo_emails
        ],
        features=[
            "Registro 24/7 de solicitudes y adjuntos.",
            "Seguimiento por estados e historial de cambios.",
            "Gestión de usuarios, categorías y reportes mensuales.",
            "Propuesta de IA para clasificación, resumen y recomendaciones.",
            "Exportación a PDF y Excel para administración.",
        ],
    )


@app.route("/propuesta-ia")
def ai_proposal():
    return render_template("ai_proposal.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = authenticate_user(request.form.get("email", ""), request.form.get("password", ""))
        if not user:
            flash("Correo o contraseña inválidos.", "error")
        else:
            login_user(user)
            flash(f"Bienvenido, {user['first_name']}.", "success")
            return redirect(url_for("dashboard"))
    return render_template("landing.html", focus_login=True)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        try:
            if request.form.get("password") != request.form.get("confirm_password"):
                raise ValueError("Las contraseñas no coinciden.")
            user = register_client(
                first_name=request.form.get("first_name", ""),
                last_name=request.form.get("last_name", ""),
                email=request.form.get("email", ""),
                phone=request.form.get("phone", ""),
                address=request.form.get("address", ""),
                password=request.form.get("password", ""),
            )
            login_user(user)
            flash("Cuenta creada correctamente. Ya puedes registrar solicitudes.", "success")
            return redirect(url_for("dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("register.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("La sesión fue cerrada.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    metrics = dashboard_metrics(g.user)
    recent_tickets = metrics["recent_tickets"]
    status_max = max((row["total"] for row in metrics["by_status"]), default=0)
    category_max = max((row["total"] for row in metrics["by_category"]), default=0)
    employee_max = max((row["total"] for row in metrics["by_employee"]), default=0)
    if g.user["role_slug"] == "client":
        subtitle = "Mis solicitudes y respuestas más recientes."
    elif g.user["role_slug"] == "employee":
        subtitle = "Gestión operativa de las solicitudes asignadas y visibles."
    else:
        subtitle = "Vista ejecutiva con indicadores, distribución y actividad reciente."
    return render_template(
        "dashboard.html",
        metrics=metrics,
        recent_tickets=recent_tickets,
        subtitle=subtitle,
        status_max=status_max,
        category_max=category_max,
        employee_max=employee_max,
    )


@app.route("/tickets")
@login_required
def tickets():
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "category_id": request.args.get("category_id", "").strip(),
        "priority": request.args.get("priority", "").strip(),
        "assigned_to": request.args.get("assigned_to", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
    }
    tickets = list_tickets(g.user, **filters)
    categories = list_categories(include_inactive=False)
    employees = list_employees()
    return render_template(
        "tickets_list.html",
        tickets=tickets,
        filters=filters,
        categories=categories,
        employees=employees,
    )


@app.route("/tickets/new", methods=["GET", "POST"])
@login_required
def new_ticket():
    if g.user["role_slug"] != "client":
        abort(403)
    categories = list_categories(include_inactive=False)
    if request.method == "POST":
        try:
            category_id = parse_int(request.form.get("category_id"))
            if not category_id:
                raise ValueError("Debes seleccionar una categoría.")
            subject = request.form.get("subject", "").strip()
            description = request.form.get("description", "").strip()
            priority = request.form.get("priority", "medium").strip()
            if not subject or not description:
                raise ValueError("El asunto y la descripción son obligatorios.")
            if priority not in ALLOWED_PRIORITIES:
                raise ValueError("La prioridad seleccionada no es válida.")
            ticket = create_ticket(
                client_id=g.user["id"],
                category_id=category_id,
                subject=subject,
                description=description,
                priority=priority,
            )
            files = request.files.getlist("attachments")
            saved, skipped = save_uploads(ticket, files, g.user["id"])
            if saved:
                flash(f"Se adjuntaron {saved} archivo(s) a la solicitud.", "success")
            if skipped:
                flash(f"{skipped} archivo(s) fueron omitidos por tipo no permitido.", "warning")
            flash(f"La solicitud {ticket['code']} fue creada correctamente.", "success")
            return redirect(url_for("ticket_detail", ticket_id=ticket["id"]))
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("ticket_new.html", categories=categories)


@app.route("/tickets/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id: int):
    ticket = get_ticket(ticket_id)
    if not can_view_ticket(g.user, ticket):
        abort(404)
    responses = get_ticket_responses(ticket_id)
    history = get_ticket_history(ticket_id)
    attachments = get_ticket_attachments(ticket_id)
    employees = list_employees()
    status_choices = ticket_status_choices(ticket) if g.user["role_slug"] != "client" else []
    return render_template(
        "ticket_detail.html",
        ticket=ticket,
        responses=responses,
        history=history,
        attachments=attachments,
        employees=employees,
        status_choices=status_choices,
        can_claim=(g.user["role_slug"] == "employee" and ticket["assigned_to"] is None and ticket["status"] != "closed"),
        can_close=(g.user["role_slug"] == "client" and ticket["status"] in {"resolved", "pending_client"}),
        average_hours=ticket_average_resolution_hours(ticket),
    )


@app.route("/tickets/<int:ticket_id>/action", methods=["POST"])
@login_required
def ticket_action(ticket_id: int):
    ticket = get_ticket(ticket_id)
    if not can_edit_ticket(g.user, ticket):
        abort(403)

    action = request.form.get("action", "")
    try:
        if action == "respond":
            body = request.form.get("body", "").strip()
            if not body:
                raise ValueError("Escribe una respuesta antes de enviarla.")
            add_response(ticket_id, g.user["id"], body)
            ticket = get_ticket(ticket_id)
            if g.user["role_slug"] in {"employee", "admin"} and ticket["status"] in {"new", "assigned"}:
                update_ticket_status(
                    ticket_id,
                    g.user["id"],
                    "in_progress",
                    note="Respuesta registrada y solicitud llevada a proceso.",
                )
            flash("La respuesta fue registrada correctamente.", "success")

        elif action == "claim":
            if g.user["role_slug"] != "employee":
                abort(403)
            claim_ticket(ticket_id, g.user["id"])
            flash("La solicitud quedó asignada a tu usuario.", "success")

        elif action == "assign":
            if g.user["role_slug"] != "admin":
                abort(403)
            employee_id = parse_int(request.form.get("employee_id"))
            if not employee_id:
                raise ValueError("Selecciona un empleado para la asignación.")
            assign_ticket(ticket_id, g.user["id"], employee_id)
            flash("La solicitud fue asignada al empleado seleccionado.", "success")

        elif action == "status":
            new_status = request.form.get("new_status", "")
            if g.user["role_slug"] == "client":
                if new_status != "closed":
                    abort(403)
                if ticket["status"] not in {"resolved", "pending_client"}:
                    raise ValueError("Solo puedes cerrar solicitudes ya resueltas o pendientes de tu confirmación.")
                rating = parse_int(request.form.get("satisfaction_rating"))
                if rating is not None and not 1 <= rating <= 5:
                    raise ValueError("La calificación debe estar entre 1 y 5.")
                comment = request.form.get("satisfaction_comment", "").strip() or None
                close_ticket(ticket_id, g.user["id"], satisfaction_rating=rating, satisfaction_comment=comment)
                flash("La solicitud fue cerrada y tu valoración fue registrada.", "success")
            else:
                update_ticket_status(ticket_id, g.user["id"], new_status, note=request.form.get("note", "").strip() or None)
                flash(f"El estado cambió a {status_label(new_status)}.", "success")

        elif action == "rate":
            if g.user["role_slug"] != "client":
                abort(403)
            rating = parse_int(request.form.get("satisfaction_rating"))
            if rating is None or not 1 <= rating <= 5:
                raise ValueError("La calificación debe estar entre 1 y 5.")
            comment = request.form.get("satisfaction_comment", "").strip() or None
            set_ticket_feedback(ticket_id, g.user["id"], rating, comment)
            flash("Tu valoración fue guardada.", "success")

        elif action == "comment":
            body = request.form.get("body", "").strip()
            if not body:
                raise ValueError("Escribe un comentario antes de enviarlo.")
            add_response(ticket_id, g.user["id"], body)
            flash("Comentario agregado al historial.", "success")

        else:
            raise ValueError("Acción no reconocida.")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("ticket_detail", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/attachments/<int:attachment_id>")
@login_required
def ticket_attachment(ticket_id: int, attachment_id: int):
    ticket = get_ticket(ticket_id)
    if not can_view_ticket(g.user, ticket):
        abort(404)
    attachment = None
    for item in get_ticket_attachments(ticket_id):
        if item["id"] == attachment_id:
            attachment = item
            break
    if not attachment:
        abort(404)
    directory = UPLOAD_DIR / ticket["code"]
    path = directory / attachment["stored_name"]
    if not path.exists():
        abort(404)
    return send_from_directory(directory, attachment["stored_name"], as_attachment=True, download_name=attachment["original_name"])


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        try:
            if request.form.get("action") == "create":
                create_user(
                    first_name=request.form.get("first_name", ""),
                    last_name=request.form.get("last_name", ""),
                    email=request.form.get("email", ""),
                    phone=request.form.get("phone", ""),
                    address=request.form.get("address", ""),
                    password=request.form.get("password", ""),
                    role_slug=request.form.get("role_slug", "client"),
                )
                flash("El usuario fue creado correctamente.", "success")
            else:
                raise ValueError("Acción de usuario no reconocida.")
        except ValueError as exc:
            flash(str(exc), "error")
    users = list_users(include_inactive=True)
    return render_template("admin_users.html", users=users, roles=list(ROLE_LABELS.items()))


@app.route("/admin/users/<int:user_id>", methods=["POST"])
@admin_required
def admin_user_update(user_id: int):
    action = request.form.get("action", "")
    try:
        if action == "update":
            role_slug = request.form.get("role_slug", "client")
            status = request.form.get("status", "active")
            password = request.form.get("password", "").strip() or None
            if user_id == g.user["id"] and status != "active":
                raise ValueError("No puedes desactivar tu propio usuario.")
            update_user(
                user_id,
                role_slug=role_slug,
                status=status,
                password=password,
            )
            flash("El usuario fue actualizado correctamente.", "success")
        elif action == "toggle":
            if user_id == g.user["id"]:
                raise ValueError("No puedes desactivar tu propio usuario.")
            user = get_user(user_id)
            new_status = "inactive" if user["status"] == "active" else "active"
            toggle_user_status(user_id, new_status)
            flash("El estado del usuario fue actualizado.", "success")
        elif action == "delete":
            remove_user(user_id, current_user_id=g.user["id"])
            flash("El usuario fue eliminado.", "success")
        else:
            raise ValueError("Acción de usuario no reconocida.")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_users"))


@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    if request.method == "POST":
        try:
            if request.form.get("action") == "create":
                create_category(
                    request.form.get("name", ""),
                    request.form.get("description", ""),
                    active=bool(request.form.get("active")),
                )
                flash("La categoría fue creada correctamente.", "success")
            else:
                raise ValueError("Acción de categoría no reconocida.")
        except ValueError as exc:
            flash(str(exc), "error")
    categories = list_categories(include_inactive=True)
    return render_template("admin_categories.html", categories=categories)


@app.route("/admin/categories/<int:category_id>", methods=["POST"])
@admin_required
def admin_category_update(category_id: int):
    action = request.form.get("action", "")
    try:
        if action == "update":
            update_category(
                category_id,
                name=request.form.get("name", ""),
                description=request.form.get("description", ""),
                active=bool(request.form.get("active")),
            )
            flash("La categoría fue actualizada.", "success")
        elif action == "delete":
            remove_category(category_id)
            flash("La categoría fue eliminada.", "success")
        else:
            raise ValueError("Acción de categoría no reconocida.")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin_categories"))


@app.route("/reports")
@admin_required
def reports_view():
    year = parse_int(request.args.get("year"), datetime.now().year) or datetime.now().year
    month = parse_int(request.args.get("month"), datetime.now().month) or datetime.now().month
    report = monthly_report(g.user, year, month)
    status_max = max((row["total"] for row in report["by_status"]), default=0)
    category_max = max((row["total"] for row in report["by_category"]), default=0)
    employee_max = max((row["total"] for row in report["by_employee"]), default=0)
    return render_template(
        "reports.html",
        report=report,
        status_max=status_max,
        category_max=category_max,
        employee_max=employee_max,
    )


@app.route("/reports/export/<fmt>")
@admin_required
def reports_export(fmt: str):
    year = parse_int(request.args.get("year"), datetime.now().year) or datetime.now().year
    month = parse_int(request.args.get("month"), datetime.now().month) or datetime.now().month
    report = monthly_report(g.user, year, month)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if fmt == "pdf":
        output = EXPORT_DIR / f"reporte_{year}_{month:02d}_{timestamp}.pdf"
        generate_pdf_report(report, output)
        return send_file(output, as_attachment=True, download_name=f"reporte_{year}_{month:02d}.pdf")
    if fmt in {"xlsx", "excel"}:
        output = EXPORT_DIR / f"reporte_{year}_{month:02d}_{timestamp}.xlsx"
        generate_excel_report(report, output)
        return send_file(output, as_attachment=True, download_name=f"reporte_{year}_{month:02d}.xlsx")
    abort(404)


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", title="Solicitud inválida", message=getattr(error, "description", "La solicitud no es válida.")), 400


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", title="Acceso denegado", message="No tienes permisos para realizar esta acción."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", title="No encontrado", message="La página o recurso solicitado no existe."), 404


def bootstrap_app() -> None:
    init_db()
    seed_demo_data()


bootstrap_app()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
