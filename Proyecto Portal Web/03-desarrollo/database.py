from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = DATA_DIR / "portal.db"

ROLE_LABELS = {
    "client": "Cliente",
    "employee": "Empleado",
    "admin": "Administrador",
}

STATUS_LABELS = {
    "new": "Nueva",
    "assigned": "Asignada",
    "in_progress": "En proceso",
    "pending_client": "Pendiente del cliente",
    "resolved": "Resuelta",
    "closed": "Cerrada",
}

STATUS_BADGES = {
    "new": "status-new",
    "assigned": "status-assigned",
    "in_progress": "status-progress",
    "pending_client": "status-pending",
    "resolved": "status-resolved",
    "closed": "status-closed",
}

PRIORITY_LABELS = {
    "low": "Baja",
    "medium": "Media",
    "high": "Alta",
    "urgent": "Crítica",
}

ALLOWED_STATUSES = tuple(STATUS_LABELS.keys())
ALLOWED_PRIORITIES = tuple(PRIORITY_LABELS.keys())

STATUS_TRANSITIONS = {
    "new": {"assigned", "in_progress", "pending_client", "resolved"},
    "assigned": {"in_progress", "pending_client", "resolved"},
    "in_progress": {"pending_client", "resolved"},
    "pending_client": {"in_progress", "resolved"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
}

DEFAULT_ROLES = (
    ("client", "Cliente", "Solicita soporte y realiza seguimiento."),
    ("employee", "Empleado", "Atiende, responde y gestiona solicitudes."),
    ("admin", "Administrador", "Gestiona usuarios, categorías y reportes."),
)

DEFAULT_CATEGORIES = (
    ("Queja", "Inconformidad con un producto, servicio o atención."),
    ("Consulta", "Solicitud de información o aclaración."),
    ("Incidente", "Falla técnica, error o interrupción del servicio."),
    ("Requerimiento", "Petición de funcionalidad, cambio o gestión."),
    ("Sugerencia", "Propuesta de mejora para el servicio."),
)

DEFAULT_USERS = (
    {
        "first_name": "Sofía",
        "last_name": "Admin",
        "email": "admin@portal.local",
        "password": "Admin123!",
        "phone": "3000000001",
        "address": "Oficina central",
        "role_slug": "admin",
    },
    {
        "first_name": "Mateo",
        "last_name": "Asesor",
        "email": "agente@portal.local",
        "password": "Agente123!",
        "phone": "3000000002",
        "address": "Mesa de servicio",
        "role_slug": "employee",
    },
    {
        "first_name": "Ana",
        "last_name": "Torres",
        "email": "cliente@portal.local",
        "password": "Cliente123!",
        "phone": "3000000003",
        "address": "Barrio Centro",
        "role_slug": "client",
    },
    {
        "first_name": "Luis",
        "last_name": "Mejía",
        "email": "cliente2@portal.local",
        "password": "Cliente123!",
        "phone": "3000000004",
        "address": "Barrio Norte",
        "role_slug": "client",
    },
)


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def to_iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    return datetime.combine(value, datetime.min.time()).isoformat(sep=" ")


def month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def month_label_es(year: int, month: int) -> str:
    names = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]
    return f"{names[month - 1]} {year}"


def _ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect() -> Iterable[sqlite3.Connection]:
    _ensure_directories()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    _ensure_directories()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS roles (
                slug TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                address TEXT,
                password_hash TEXT NOT NULL,
                role_slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY (role_slug) REFERENCES roles (slug)
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                client_id INTEGER NOT NULL,
                assigned_to INTEGER,
                category_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                satisfaction_rating INTEGER,
                satisfaction_comment TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                FOREIGN KEY (client_id) REFERENCES users (id),
                FOREIGN KEY (assigned_to) REFERENCES users (id) ON DELETE SET NULL,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            );

            CREATE TABLE IF NOT EXISTS ticket_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES users (id)
            );

            CREATE TABLE IF NOT EXISTS ticket_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                actor_id INTEGER,
                action TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
                FOREIGN KEY (actor_id) REFERENCES users (id)
            );

            CREATE TABLE IF NOT EXISTS ticket_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                mime_type TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES users (id)
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_client ON tickets (client_id);
            CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets (assigned_to);
            CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status);
            CREATE INDEX IF NOT EXISTS idx_tickets_category ON tickets (category_id);
            """
        )


def seed_demo_data() -> None:
    with connect() as conn:
        for slug, name, description in DEFAULT_ROLES:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles (slug, name, description)
                VALUES (?, ?, ?)
                """,
                (slug, name, description),
            )

        for category_name, description in DEFAULT_CATEGORIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO categories (name, description, active)
                VALUES (?, ?, 1)
                """,
                (category_name, description),
            )

        for user in DEFAULT_USERS:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (
                    first_name, last_name, email, phone, address,
                    password_hash, role_slug, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    user["first_name"],
                    user["last_name"],
                    user["email"],
                    user["phone"],
                    user["address"],
                    generate_password_hash(user["password"]),
                    user["role_slug"],
                    now_iso(),
                ),
            )

    with connect() as conn:
        ticket_count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        if ticket_count:
            return

        admin = get_user_by_email("admin@portal.local")
        employee = get_user_by_email("agente@portal.local")
        client_one = get_user_by_email("cliente@portal.local")
        client_two = get_user_by_email("cliente2@portal.local")

        categories = {row["name"]: row["id"] for row in list_categories()}
        base_now = datetime.now().replace(microsecond=0)
        seeds = [
            {
                "client_id": client_one["id"],
                "assigned_to": employee["id"],
                "category_id": categories["Queja"],
                "subject": "Producto defectuoso recibido",
                "description": "El producto llegó con una pieza rota y no enciende correctamente.",
                "priority": "high",
                "status": "closed",
                "created_at": base_now - timedelta(days=18),
                "closed_at": base_now - timedelta(days=15),
                "satisfaction_rating": 5,
                "satisfaction_comment": "Respuesta rápida y solución satisfactoria.",
                "responses": [
                    ("employee", "Gracias por el reporte. Ya iniciamos el proceso de revisión."),
                    ("client", "Adjunto fotografías del daño para soporte."),
                    ("employee", "Validamos el caso y enviamos reemplazo sin costo."),
                ],
                "history": [
                    ("created", None, "new", "Solicitud creada"),
                    ("assigned", "new", "assigned", "Asignada al equipo de atención"),
                    ("status_changed", "assigned", "in_progress", "Caso en proceso"),
                    ("status_changed", "in_progress", "resolved", "Solución aprobada"),
                    ("closed", "resolved", "closed", "Cierre confirmado por el cliente"),
                ],
            },
            {
                "client_id": client_one["id"],
                "assigned_to": employee["id"],
                "category_id": categories["Consulta"],
                "subject": "Cambio de dirección de entrega",
                "description": "Necesito actualizar la dirección antes de que el pedido sea despachado.",
                "priority": "medium",
                "status": "in_progress",
                "created_at": base_now - timedelta(days=7),
                "responses": [
                    ("employee", "Estamos validando la orden y el estado del despacho."),
                ],
                "history": [
                    ("created", None, "new", "Solicitud creada"),
                    ("assigned", "new", "assigned", "Asignada al asesor"),
                    ("status_changed", "assigned", "in_progress", "Actualización en curso"),
                ],
            },
            {
                "client_id": client_two["id"],
                "assigned_to": employee["id"],
                "category_id": categories["Incidente"],
                "subject": "Error al iniciar sesión",
                "description": "La cuenta muestra un mensaje de credenciales inválidas aunque la clave es correcta.",
                "priority": "high",
                "status": "pending_client",
                "created_at": base_now - timedelta(days=3),
                "responses": [
                    ("employee", "Revisamos la cuenta. Necesitamos que confirme el correo de recuperación."),
                ],
                "history": [
                    ("created", None, "new", "Solicitud creada"),
                    ("assigned", "new", "assigned", "Asignada al asesor"),
                    ("status_changed", "assigned", "in_progress", "Validación técnica"),
                    ("status_changed", "in_progress", "pending_client", "Esperando confirmación del cliente"),
                ],
            },
            {
                "client_id": client_two["id"],
                "assigned_to": None,
                "category_id": categories["Requerimiento"],
                "subject": "Agregar comprobante de pago",
                "description": "Solicito que se active la opción para adjuntar comprobantes directamente desde la solicitud.",
                "priority": "low",
                "status": "new",
                "created_at": base_now - timedelta(days=1),
                "responses": [],
                "history": [
                    ("created", None, "new", "Solicitud creada"),
                ],
            },
            {
                "client_id": client_one["id"],
                "assigned_to": employee["id"],
                "category_id": categories["Sugerencia"],
                "subject": "Avisos por correo más claros",
                "description": "Los correos de respuesta podrían incluir un resumen del estado y el siguiente paso.",
                "priority": "medium",
                "status": "resolved",
                "created_at": base_now - timedelta(days=11),
                "responses": [
                    ("employee", "Gracias por la sugerencia. La incluiremos en la próxima iteración."),
                ],
                "history": [
                    ("created", None, "new", "Solicitud creada"),
                    ("assigned", "new", "assigned", "Asignada al asesor"),
                    ("status_changed", "assigned", "resolved", "Respuesta entregada"),
                ],
            },
            {
                "client_id": client_two["id"],
                "assigned_to": employee["id"],
                "category_id": categories["Queja"],
                "subject": "Demora en la entrega",
                "description": "El pedido tardó más de lo prometido y no recibimos seguimiento oportuno.",
                "priority": "high",
                "status": "closed",
                "created_at": base_now - timedelta(days=33),
                "closed_at": base_now - timedelta(days=28),
                "satisfaction_rating": 4,
                "satisfaction_comment": "La gestión final fue buena, aunque la demora inicial afectó la experiencia.",
                "responses": [
                    ("employee", "Estamos revisando el número de guía y la trazabilidad del envío."),
                    ("employee", "El pedido fue entregado y el cliente aceptó el cierre."),
                ],
                "history": [
                    ("created", None, "new", "Solicitud creada"),
                    ("assigned", "new", "assigned", "Asignada al asesor"),
                    ("status_changed", "assigned", "in_progress", "Seguimiento a transporte"),
                    ("status_changed", "in_progress", "resolved", "Compensación aplicada"),
                    ("closed", "resolved", "closed", "Caso cerrado"),
                ],
            },
        ]

        for seed in seeds:
            ticket_id = _insert_ticket(
                conn,
                client_id=seed["client_id"],
                assigned_to=seed.get("assigned_to"),
                category_id=seed["category_id"],
                subject=seed["subject"],
                description=seed["description"],
                priority=seed["priority"],
                status=seed["status"],
                created_at=to_iso(seed["created_at"]),
                updated_at=to_iso(seed["created_at"]),
                closed_at=to_iso(seed.get("closed_at")),
                satisfaction_rating=seed.get("satisfaction_rating"),
                satisfaction_comment=seed.get("satisfaction_comment"),
            )
            ticket = conn.execute("SELECT code FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            code = f"SOL-{ticket_id:06d}"
            conn.execute("UPDATE tickets SET code = ? WHERE id = ?", (code, ticket_id))

            for role, body in seed["responses"]:
                author = employee if role == "employee" else (
                    client_one if seed["client_id"] == client_one["id"] else client_two
                )
                conn.execute(
                    """
                    INSERT INTO ticket_responses (ticket_id, author_id, body, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ticket_id, author["id"], body, to_iso(seed["created_at"] + timedelta(hours=2))),
                )

            for index, (action, from_status, to_status, note) in enumerate(seed["history"], start=1):
                created_at = seed["created_at"] + timedelta(hours=index)
                conn.execute(
                    """
                    INSERT INTO ticket_history (
                        ticket_id, actor_id, action, from_status, to_status, note, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        employee["id"] if action != "created" else seed["client_id"],
                        action,
                        from_status,
                        to_status,
                        note,
                        to_iso(created_at),
                    ),
                )


def _insert_ticket(
    conn: sqlite3.Connection,
    *,
    client_id: int,
    category_id: int,
    subject: str,
    description: str,
    priority: str,
    status: str = "new",
    assigned_to: int | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    closed_at: str | None = None,
    satisfaction_rating: int | None = None,
    satisfaction_comment: str | None = None,
) -> int:
    created_at = created_at or now_iso()
    updated_at = updated_at or created_at
    cur = conn.execute(
        """
        INSERT INTO tickets (
            client_id, assigned_to, category_id, subject, description,
            priority, status, satisfaction_rating, satisfaction_comment,
            created_at, updated_at, closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            client_id,
            assigned_to,
            category_id,
            subject,
            description,
            priority,
            status,
            satisfaction_rating,
            satisfaction_comment,
            created_at,
            updated_at,
            closed_at,
        ),
    )
    ticket_id = int(cur.lastrowid)
    conn.execute("UPDATE tickets SET code = ? WHERE id = ?", (f"SOL-{ticket_id:06d}", ticket_id))
    return ticket_id


def create_ticket(
    client_id: int,
    category_id: int,
    subject: str,
    description: str,
    priority: str,
    *,
    assigned_to: int | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        ticket_id = _insert_ticket(
            conn,
            client_id=client_id,
            category_id=category_id,
            subject=subject,
            description=description,
            priority=priority,
            status="new",
            assigned_to=assigned_to,
        )
        record_history(
            conn,
            ticket_id=ticket_id,
            actor_id=client_id,
            action="created",
            from_status=None,
            to_status="new",
            note="Solicitud registrada por el cliente",
        )
    return get_ticket(ticket_id)


def record_history(
    conn: sqlite3.Connection,
    *,
    ticket_id: int,
    actor_id: int | None,
    action: str,
    from_status: str | None,
    to_status: str | None,
    note: str | None,
    created_at: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ticket_history (
            ticket_id, actor_id, action, from_status, to_status, note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            actor_id,
            action,
            from_status,
            to_status,
            note,
            created_at or now_iso(),
        ),
    )
    conn.execute(
        "UPDATE tickets SET updated_at = ? WHERE id = ?",
        (created_at or now_iso(), ticket_id),
    )


def add_response(ticket_id: int, author_id: int, body: str) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO ticket_responses (ticket_id, author_id, body, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (ticket_id, author_id, body, now_iso()),
        )
        ticket = get_ticket(ticket_id)
        if ticket and ticket["status"] == "pending_client":
            conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
                ("in_progress", now_iso(), ticket_id),
            )
            record_history(
                conn,
                ticket_id=ticket_id,
                actor_id=author_id,
                action="status_changed",
                from_status="pending_client",
                to_status="in_progress",
                note="El cliente respondió y el caso volvió a proceso",
            )
        else:
            conn.execute(
                "UPDATE tickets SET updated_at = ? WHERE id = ?",
                (now_iso(), ticket_id),
            )
        record_history(
            conn,
            ticket_id=ticket_id,
            actor_id=author_id,
            action="response",
            from_status=ticket["status"] if ticket else None,
            to_status=ticket["status"] if ticket else None,
            note="Se agregó una respuesta al ticket",
        )
    return get_ticket(ticket_id)


def add_attachment(
    ticket_id: int,
    author_id: int,
    original_name: str,
    stored_name: str,
    mime_type: str | None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO ticket_attachments (
                ticket_id, author_id, original_name, stored_name, mime_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, author_id, original_name, stored_name, mime_type, now_iso()),
        )
        conn.execute(
            "UPDATE tickets SET updated_at = ? WHERE id = ?",
            (now_iso(), ticket_id),
        )


def assign_ticket(ticket_id: int, actor_id: int, employee_id: int) -> dict[str, Any]:
    with connect() as conn:
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise ValueError("La solicitud no existe.")
        from_status = ticket["status"]
        new_status = "assigned" if ticket["status"] == "new" else ticket["status"]
        conn.execute(
            """
            UPDATE tickets
            SET assigned_to = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (employee_id, new_status, now_iso(), ticket_id),
        )
        record_history(
            conn,
            ticket_id=ticket_id,
            actor_id=actor_id,
            action="assigned",
            from_status=from_status,
            to_status=new_status,
            note="Solicitud asignada a un empleado",
        )
    return get_ticket(ticket_id)


def claim_ticket(ticket_id: int, employee_id: int) -> dict[str, Any]:
    return assign_ticket(ticket_id=ticket_id, actor_id=employee_id, employee_id=employee_id)


def update_ticket_status(
    ticket_id: int,
    actor_id: int,
    new_status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    if new_status not in STATUS_LABELS:
        raise ValueError("Estado inválido.")
    with connect() as conn:
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise ValueError("La solicitud no existe.")
        current = ticket["status"]
        if new_status != current and new_status not in STATUS_TRANSITIONS[current]:
            raise ValueError("La transición de estado no está permitida.")
        closed_at = ticket["closed_at"]
        if new_status == "closed" and not closed_at:
            closed_at = now_iso()
        if new_status != "closed":
            closed_at = None
        conn.execute(
            """
            UPDATE tickets
            SET status = ?, closed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, closed_at, now_iso(), ticket_id),
        )
        record_history(
            conn,
            ticket_id=ticket_id,
            actor_id=actor_id,
            action="status_changed",
            from_status=current,
            to_status=new_status,
            note=note or f"Estado cambiado a {STATUS_LABELS[new_status]}",
        )
    return get_ticket(ticket_id)


def close_ticket(
    ticket_id: int,
    actor_id: int,
    *,
    satisfaction_rating: int | None = None,
    satisfaction_comment: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise ValueError("La solicitud no existe.")
        conn.execute(
            """
            UPDATE tickets
            SET status = 'closed',
                closed_at = COALESCE(closed_at, ?),
                satisfaction_rating = COALESCE(?, satisfaction_rating),
                satisfaction_comment = COALESCE(?, satisfaction_comment),
                updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), satisfaction_rating, satisfaction_comment, now_iso(), ticket_id),
        )
        record_history(
            conn,
            ticket_id=ticket_id,
            actor_id=actor_id,
            action="closed",
            from_status=ticket["status"],
            to_status="closed",
            note="La solicitud fue cerrada por el cliente",
        )
        if satisfaction_rating is not None:
            record_history(
                conn,
                ticket_id=ticket_id,
                actor_id=actor_id,
                action="rated",
                from_status="closed",
                to_status="closed",
                note=f"Calificación enviada: {satisfaction_rating}/5",
            )
    return get_ticket(ticket_id)


def set_ticket_feedback(
    ticket_id: int,
    actor_id: int,
    rating: int,
    comment: str | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            """
            UPDATE tickets
            SET satisfaction_rating = ?, satisfaction_comment = ?, updated_at = ?
            WHERE id = ?
            """,
            (rating, comment, now_iso(), ticket_id),
        )
        record_history(
            conn,
            ticket_id=ticket_id,
            actor_id=actor_id,
            action="rated",
            from_status="closed",
            to_status="closed",
            note=f"Calificación registrada: {rating}/5",
        )
    return get_ticket(ticket_id)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)
    if not user or user["status"] != "active":
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    return user


def register_client(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    address: str,
    password: str,
) -> dict[str, Any]:
    return create_user(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        address=address,
        password=password,
        role_slug="client",
    )


def create_user(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str = "",
    address: str = "",
    password: str,
    role_slug: str,
    status: str = "active",
) -> dict[str, Any]:
    if role_slug not in ROLE_LABELS:
        raise ValueError("Rol inválido.")
    with connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if existing:
            raise ValueError("Ya existe un usuario con ese correo.")
        conn.execute(
            """
            INSERT INTO users (
                first_name, last_name, email, phone, address,
                password_hash, role_slug, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                first_name.strip(),
                last_name.strip(),
                email.strip().lower(),
                phone.strip(),
                address.strip(),
                generate_password_hash(password),
                role_slug,
                status,
                now_iso(),
            ),
        )
    return get_user_by_email(email)


def update_user(
    user_id: int,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    role_slug: str | None = None,
    status: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    updates: list[str] = []
    params: list[Any] = []
    if first_name is not None:
        updates.append("first_name = ?")
        params.append(first_name.strip())
    if last_name is not None:
        updates.append("last_name = ?")
        params.append(last_name.strip())
    if email is not None:
        updates.append("email = ?")
        params.append(email.strip().lower())
    if phone is not None:
        updates.append("phone = ?")
        params.append(phone.strip())
    if address is not None:
        updates.append("address = ?")
        params.append(address.strip())
    if role_slug is not None:
        if role_slug not in ROLE_LABELS:
            raise ValueError("Rol inválido.")
        updates.append("role_slug = ?")
        params.append(role_slug)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if password:
        updates.append("password_hash = ?")
        params.append(generate_password_hash(password))
    if not updates:
        return get_user(user_id)
    params.append(user_id)
    with connect() as conn:
        if email is not None:
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email.strip().lower(), user_id),
            ).fetchone()
            if existing:
                raise ValueError("Ya existe un usuario con ese correo.")
        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    return get_user(user_id)


def toggle_user_status(user_id: int, status: str) -> dict[str, Any]:
    if status not in {"active", "inactive"}:
        raise ValueError("Estado de usuario inválido.")
    with connect() as conn:
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    return get_user(user_id)


def remove_user(user_id: int, *, current_user_id: int | None = None) -> None:
    if current_user_id is not None and user_id == current_user_id:
        raise ValueError("No puedes eliminar tu propio usuario.")
    with connect() as conn:
        related = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM tickets WHERE client_id = ? OR assigned_to = ?) AS ticket_count,
                (SELECT COUNT(*) FROM ticket_responses WHERE author_id = ?) AS response_count,
                (SELECT COUNT(*) FROM ticket_history WHERE actor_id = ?) AS history_count,
                (SELECT COUNT(*) FROM ticket_attachments WHERE author_id = ?) AS attachment_count
            """,
            (user_id, user_id, user_id, user_id, user_id),
        ).fetchone()
        if any(related):
            raise ValueError("El usuario tiene actividad asociada y solo puede desactivarse.")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def create_category(name: str, description: str, active: bool = True) -> dict[str, Any]:
    with connect() as conn:
        existing = conn.execute("SELECT id FROM categories WHERE lower(name) = lower(?)", (name.strip(),)).fetchone()
        if existing:
            raise ValueError("Ya existe una categoría con ese nombre.")
        conn.execute(
            "INSERT INTO categories (name, description, active) VALUES (?, ?, ?)",
            (name.strip(), description.strip(), 1 if active else 0),
        )
    return get_category_by_name(name)


def update_category(
    category_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    updates: list[str] = []
    params: list[Any] = []
    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())
    if description is not None:
        updates.append("description = ?")
        params.append(description.strip())
    if active is not None:
        updates.append("active = ?")
        params.append(1 if active else 0)
    if not updates:
        return get_category(category_id)
    params.append(category_id)
    with connect() as conn:
        if name is not None:
            existing = conn.execute(
                "SELECT id FROM categories WHERE lower(name) = lower(?) AND id != ?",
                (name.strip(), category_id),
            ).fetchone()
            if existing:
                raise ValueError("Ya existe una categoría con ese nombre.")
        conn.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params)
    return get_category(category_id)


def remove_category(category_id: int) -> None:
    with connect() as conn:
        in_use = conn.execute("SELECT COUNT(*) FROM tickets WHERE category_id = ?", (category_id,)).fetchone()[0]
        if in_use:
            raise ValueError("No se puede eliminar una categoría con solicitudes asociadas.")
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))


def get_user(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT u.*, r.name AS role_name, r.description AS role_description
            FROM users u
            JOIN roles r ON r.slug = u.role_slug
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT u.*, r.name AS role_name, r.description AS role_description
            FROM users u
            JOIN roles r ON r.slug = u.role_slug
            WHERE lower(u.email) = lower(?)
            """,
            (email.strip(),),
        ).fetchone()
        return dict(row) if row else None


def list_users(*, include_inactive: bool = True, role_slug: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_inactive:
        clauses.append("u.status = 'active'")
    if role_slug:
        clauses.append("u.role_slug = ?")
        params.append(role_slug)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT u.*, r.name AS role_name, r.description AS role_description
            FROM users u
            JOIN roles r ON r.slug = u.role_slug
            {where_sql}
            ORDER BY u.role_slug, u.first_name, u.last_name
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def list_employees(*, active_only: bool = True) -> list[dict[str, Any]]:
    clauses = ["u.role_slug = 'employee'"]
    params: list[Any] = []
    if active_only:
        clauses.append("u.status = 'active'")
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT u.*, r.name AS role_name
            FROM users u
            JOIN roles r ON r.slug = u.role_slug
            WHERE {' AND '.join(clauses)}
            ORDER BY u.first_name, u.last_name
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def list_categories(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    where_sql = "" if include_inactive else "WHERE active = 1"
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM categories
            {where_sql}
            ORDER BY active DESC, name
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_category(category_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
        return dict(row) if row else None


def get_category_by_name(name: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM categories WHERE lower(name) = lower(?)",
            (name.strip(),),
        ).fetchone()
        return dict(row) if row else None


def get_ticket(ticket_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                t.*,
                c.first_name || ' ' || c.last_name AS client_name,
                c.email AS client_email,
                c.phone AS client_phone,
                c.address AS client_address,
                e.first_name || ' ' || e.last_name AS employee_name,
                e.email AS employee_email,
                cat.name AS category_name,
                cat.description AS category_description,
                (SELECT COUNT(*) FROM ticket_responses tr WHERE tr.ticket_id = t.id) AS response_count,
                (SELECT COUNT(*) FROM ticket_attachments ta WHERE ta.ticket_id = t.id) AS attachment_count
            FROM tickets t
            JOIN users c ON c.id = t.client_id
            LEFT JOIN users e ON e.id = t.assigned_to
            JOIN categories cat ON cat.id = t.category_id
            WHERE t.id = ?
            """,
            (ticket_id,),
        ).fetchone()
        return dict(row) if row else None


def get_ticket_by_code(code: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                t.*,
                c.first_name || ' ' || c.last_name AS client_name,
                c.email AS client_email,
                c.phone AS client_phone,
                c.address AS client_address,
                e.first_name || ' ' || e.last_name AS employee_name,
                e.email AS employee_email,
                cat.name AS category_name,
                cat.description AS category_description,
                (SELECT COUNT(*) FROM ticket_responses tr WHERE tr.ticket_id = t.id) AS response_count,
                (SELECT COUNT(*) FROM ticket_attachments ta WHERE ta.ticket_id = t.id) AS attachment_count
            FROM tickets t
            JOIN users c ON c.id = t.client_id
            LEFT JOIN users e ON e.id = t.assigned_to
            JOIN categories cat ON cat.id = t.category_id
            WHERE lower(t.code) = lower(?)
            """,
            (code.strip(),),
        ).fetchone()
        return dict(row) if row else None


def get_ticket_responses(ticket_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT tr.*, u.first_name || ' ' || u.last_name AS author_name, u.role_slug AS author_role
            FROM ticket_responses tr
            JOIN users u ON u.id = tr.author_id
            WHERE tr.ticket_id = ?
            ORDER BY tr.created_at ASC, tr.id ASC
            """,
            (ticket_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_ticket_history(ticket_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT th.*, u.first_name || ' ' || u.last_name AS actor_name, u.role_slug AS actor_role
            FROM ticket_history th
            LEFT JOIN users u ON u.id = th.actor_id
            WHERE th.ticket_id = ?
            ORDER BY th.created_at ASC, th.id ASC
            """,
            (ticket_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_ticket_attachments(ticket_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT ta.*, u.first_name || ' ' || u.last_name AS author_name
            FROM ticket_attachments ta
            JOIN users u ON u.id = ta.author_id
            WHERE ta.ticket_id = ?
            ORDER BY ta.created_at ASC, ta.id ASC
            """,
            (ticket_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def _ticket_scope_clause(user: dict[str, Any]) -> tuple[str, list[Any]]:
    if user["role_slug"] == "client":
        return "t.client_id = ?", [user["id"]]
    return "1 = 1", []


def list_tickets(
    user: dict[str, Any],
    *,
    q: str = "",
    status: str = "",
    category_id: str = "",
    priority: str = "",
    assigned_to: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int | None = 200,
) -> list[dict[str, Any]]:
    where_clauses: list[str] = []
    params: list[Any] = []

    scope_sql, scope_params = _ticket_scope_clause(user)
    where_clauses.append(scope_sql)
    params.extend(scope_params)

    if q.strip():
        where_clauses.append(
            """
            (
                t.code LIKE ? OR
                t.subject LIKE ? OR
                t.description LIKE ? OR
                c.first_name LIKE ? OR
                c.last_name LIKE ? OR
                c.email LIKE ? OR
                COALESCE(e.first_name, '') LIKE ? OR
                COALESCE(e.last_name, '') LIKE ? OR
                COALESCE(e.email, '') LIKE ?
            )
            """
        )
        like = f"%{q.strip()}%"
        params.extend([like] * 9)
    if status:
        where_clauses.append("t.status = ?")
        params.append(status)
    if category_id:
        where_clauses.append("t.category_id = ?")
        params.append(category_id)
    if priority:
        where_clauses.append("t.priority = ?")
        params.append(priority)
    if assigned_to:
        where_clauses.append("t.assigned_to = ?")
        params.append(assigned_to)
    if date_from:
        where_clauses.append("date(t.created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        where_clauses.append("date(t.created_at) <= date(?)")
        params.append(date_to)

    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.*,
                c.first_name || ' ' || c.last_name AS client_name,
                c.email AS client_email,
                e.first_name || ' ' || e.last_name AS employee_name,
                e.email AS employee_email,
                cat.name AS category_name,
                cat.description AS category_description,
                (SELECT COUNT(*) FROM ticket_responses tr WHERE tr.ticket_id = t.id) AS response_count,
                (SELECT COUNT(*) FROM ticket_attachments ta WHERE ta.ticket_id = t.id) AS attachment_count,
                (SELECT MAX(created_at) FROM ticket_responses tr WHERE tr.ticket_id = t.id) AS last_response_at
            FROM tickets t
            JOIN users c ON c.id = t.client_id
            LEFT JOIN users e ON e.id = t.assigned_to
            JOIN categories cat ON cat.id = t.category_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY datetime(t.updated_at) DESC, t.id DESC
            {limit_sql}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def dashboard_metrics(user: dict[str, Any]) -> dict[str, Any]:
    scope_sql, params = _ticket_scope_clause(user)
    with connect() as conn:
        totals = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_tickets,
                SUM(CASE WHEN t.status != 'closed' THEN 1 ELSE 0 END) AS open_tickets,
                SUM(CASE WHEN t.status = 'closed' THEN 1 ELSE 0 END) AS closed_tickets,
                SUM(CASE WHEN t.status = 'pending_client' THEN 1 ELSE 0 END) AS pending_client,
                SUM(CASE WHEN date(t.created_at) = date('now') THEN 1 ELSE 0 END) AS today_tickets,
                SUM(CASE WHEN strftime('%Y-%m', t.created_at) = strftime('%Y-%m', 'now') THEN 1 ELSE 0 END) AS month_tickets,
                ROUND(AVG(CASE WHEN t.closed_at IS NOT NULL THEN (julianday(t.closed_at) - julianday(t.created_at)) * 24.0 END), 2) AS avg_resolution_hours,
                ROUND(AVG(CASE WHEN t.satisfaction_rating IS NOT NULL THEN t.satisfaction_rating END), 2) AS satisfaction_avg
            FROM tickets t
            WHERE {scope_sql}
            """,
            params,
        ).fetchone()

        status_rows = conn.execute(
            f"""
            SELECT t.status, COUNT(*) AS total
            FROM tickets t
            WHERE {scope_sql}
            GROUP BY t.status
            ORDER BY total DESC, t.status
            """,
            params,
        ).fetchall()

        category_rows = conn.execute(
            f"""
            SELECT cat.name, COUNT(*) AS total
            FROM tickets t
            JOIN categories cat ON cat.id = t.category_id
            WHERE {scope_sql}
            GROUP BY cat.id
            ORDER BY total DESC, cat.name
            LIMIT 6
            """,
            params,
        ).fetchall()

        employee_rows = []
        if user["role_slug"] != "client":
            employee_rows = conn.execute(
                """
                SELECT
                    COALESCE(u.first_name || ' ' || u.last_name, 'Sin asignar') AS name,
                    COUNT(t.id) AS total
                FROM tickets t
                LEFT JOIN users u ON u.id = t.assigned_to
                GROUP BY u.id
                ORDER BY total DESC, name
                LIMIT 6
                """
            ).fetchall()

        recent_rows = conn.execute(
            f"""
            SELECT
                t.*,
                c.first_name || ' ' || c.last_name AS client_name,
                e.first_name || ' ' || e.last_name AS employee_name,
                cat.name AS category_name
            FROM tickets t
            JOIN users c ON c.id = t.client_id
            LEFT JOIN users e ON e.id = t.assigned_to
            JOIN categories cat ON cat.id = t.category_id
            WHERE {scope_sql}
            ORDER BY datetime(t.updated_at) DESC, t.id DESC
            LIMIT 6
            """,
            params,
        ).fetchall()

    return {
        "summary": {key: totals[key] for key in totals.keys()},
        "by_status": [dict(row) for row in status_rows],
        "by_category": [dict(row) for row in category_rows],
        "by_employee": [dict(row) for row in employee_rows],
        "recent_tickets": [dict(row) for row in recent_rows],
    }


def monthly_report(user: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    start, end = month_bounds(year, month)
    scope_sql, scope_params = _ticket_scope_clause(user)
    params = [*scope_params, start, end]

    with connect() as conn:
        totals = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_tickets,
                SUM(CASE WHEN t.status = 'closed' THEN 1 ELSE 0 END) AS closed_tickets,
                SUM(CASE WHEN t.status != 'closed' THEN 1 ELSE 0 END) AS open_tickets,
                SUM(CASE WHEN t.status = 'pending_client' THEN 1 ELSE 0 END) AS pending_client,
                ROUND(AVG(CASE WHEN t.closed_at IS NOT NULL THEN (julianday(t.closed_at) - julianday(t.created_at)) * 24.0 END), 2) AS avg_resolution_hours,
                ROUND(AVG(CASE WHEN t.satisfaction_rating IS NOT NULL THEN t.satisfaction_rating END), 2) AS satisfaction_avg
            FROM tickets t
            WHERE {scope_sql}
              AND date(t.created_at) >= date(?)
              AND date(t.created_at) < date(?)
            """,
            params,
        ).fetchone()

        by_status = conn.execute(
            f"""
            SELECT t.status, COUNT(*) AS total
            FROM tickets t
            WHERE {scope_sql}
              AND date(t.created_at) >= date(?)
              AND date(t.created_at) < date(?)
            GROUP BY t.status
            ORDER BY total DESC, t.status
            """,
            params,
        ).fetchall()

        by_category = conn.execute(
            f"""
            SELECT cat.name, COUNT(*) AS total
            FROM tickets t
            JOIN categories cat ON cat.id = t.category_id
            WHERE {scope_sql}
              AND date(t.created_at) >= date(?)
              AND date(t.created_at) < date(?)
            GROUP BY cat.id
            ORDER BY total DESC, cat.name
            """,
            params,
        ).fetchall()

        by_employee = conn.execute(
            f"""
            SELECT
                COALESCE(u.first_name || ' ' || u.last_name, 'Sin asignar') AS name,
                COUNT(t.id) AS total
            FROM tickets t
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE {scope_sql}
              AND date(t.created_at) >= date(?)
              AND date(t.created_at) < date(?)
            GROUP BY u.id
            ORDER BY total DESC, name
            """,
            params,
        ).fetchall()

        tickets = conn.execute(
            f"""
            SELECT
                t.*,
                c.first_name || ' ' || c.last_name AS client_name,
                e.first_name || ' ' || e.last_name AS employee_name,
                cat.name AS category_name
            FROM tickets t
            JOIN users c ON c.id = t.client_id
            LEFT JOIN users e ON e.id = t.assigned_to
            JOIN categories cat ON cat.id = t.category_id
            WHERE {scope_sql}
              AND date(t.created_at) >= date(?)
              AND date(t.created_at) < date(?)
            ORDER BY datetime(t.created_at) DESC, t.id DESC
            """,
            params,
        ).fetchall()

    return {
        "year": year,
        "month": month,
        "label": month_label_es(year, month),
        "period_start": start,
        "period_end": end,
        "summary": {key: totals[key] for key in totals.keys()},
        "by_status": [dict(row) for row in by_status],
        "by_category": [dict(row) for row in by_category],
        "by_employee": [dict(row) for row in by_employee],
        "tickets": [dict(row) for row in tickets],
    }


def format_money(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def ticket_average_resolution_hours(ticket: dict[str, Any]) -> float | None:
    if not ticket.get("closed_at"):
        return None
    opened = datetime.fromisoformat(ticket["created_at"])
    closed = datetime.fromisoformat(ticket["closed_at"])
    return round((closed - opened).total_seconds() / 3600, 2)
