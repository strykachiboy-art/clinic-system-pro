from __future__ import annotations

from sqlalchemy import or_, select

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.department_enums import DepartmentStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.clinic.models.clinic_model import Clinic
from app.modules.department.models.department_model import Department


def _validate_positive_id(
    value,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
    ):
        raise ValidationError(
            f"{field_name} must be an integer"
        )

    if value <= 0:
        raise ValidationError(
            f"Invalid {field_name}"
        )

    return value


def _validate_text(
    value,
    field_name: str,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        raise ValidationError(
            f"{field_name} is required"
        )

    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed {max_length} characters"
        )

    return value


def _normalize_code(code: str) -> str:
    return _validate_text(
        code,
        "Department code",
        100,
    ).upper()


def _normalize_name(name: str) -> str:
    return _validate_text(
        name,
        "Department name",
        150,
    )


def _normalize_description(
    description: str | None,
) -> str | None:
    if description is None:
        return None

    if not isinstance(description, str):
        raise ValidationError(
            "Department description must be a string"
        )

    description = description.strip()

    if not description:
        return None

    if len(description) > 5000:
        raise ValidationError(
            "Department description cannot exceed 5000 characters"
        )

    return description


def _validate_status(
    status,
) -> DepartmentStatus:
    if isinstance(status, DepartmentStatus):
        return status

    try:
        return DepartmentStatus(status)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid department status"
        ) from exc


def _get_clinic(
    clinic_id: int,
    *,
    for_update: bool = False,
) -> Clinic:
    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic ID",
    )

    statement = select(Clinic).where(
        Clinic.id == clinic_id,
    )

    if for_update:
        statement = statement.with_for_update()

    clinic = db.session.execute(
        statement
    ).scalar_one_or_none()

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def _ensure_active_clinic(
    clinic: Clinic,
) -> None:
    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic.id} is not active"
        )


def _get_department(
    clinic_id: int,
    department_id: int,
    *,
    for_update: bool = False,
) -> Department:
    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic ID",
    )

    department_id = _validate_positive_id(
        department_id,
        "department ID",
    )

    statement = select(Department).where(
        Department.id == department_id,
        Department.clinic_id == clinic_id,
    )

    if for_update:
        statement = statement.with_for_update()

    department = db.session.execute(
        statement
    ).scalar_one_or_none()

    if department is None:
        raise NotFoundError(
            f"Department {department_id} not found"
        )

    return department


def _ensure_unique_code(
    clinic_id: int,
    code: str,
    *,
    exclude_department_id: int | None = None,
) -> None:
    statement = select(
        Department.id
    ).where(
        Department.clinic_id == clinic_id,
        Department.code == code,
    )

    if exclude_department_id is not None:
        statement = statement.where(
            Department.id != exclude_department_id,
        )

    existing_id = db.session.execute(
        statement.limit(1)
    ).scalar_one_or_none()

    if existing_id is not None:
        raise ConflictError(
            f"Department code '{code}' already exists "
            f"in clinic {clinic_id}"
        )


def _ensure_unique_name(
    clinic_id: int,
    name: str,
    *,
    exclude_department_id: int | None = None,
) -> None:
    statement = select(
        Department.id
    ).where(
        Department.clinic_id == clinic_id,
        Department.name == name,
    )

    if exclude_department_id is not None:
        statement = statement.where(
            Department.id != exclude_department_id,
        )

    existing_id = db.session.execute(
        statement.limit(1)
    ).scalar_one_or_none()

    if existing_id is not None:
        raise ConflictError(
            f"Department name '{name}' already exists "
            f"in clinic {clinic_id}"
        )


def get_department(
    clinic_id: int,
    department_id: int,
) -> Department:
    return _get_department(
        clinic_id=clinic_id,
        department_id=department_id,
    )


def list_departments(
    clinic_id: int,
    status: DepartmentStatus | None = None,
    search: str | None = None,
) -> list[Department]:
    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic ID",
    )

    _get_clinic(clinic_id)

    if status is not None:
        status = _validate_status(status)

    if search is not None:
        if not isinstance(search, str):
            raise ValidationError(
                "Department search must be a string"
            )

        search = search.strip()

    statement = select(Department).where(
        Department.clinic_id == clinic_id,
    )

    if status is not None:
        statement = statement.where(
            Department.status == status,
        )

    if search:
        like = f"%{search}%"

        statement = statement.where(
            or_(
                Department.code.ilike(like),
                Department.name.ilike(like),
                Department.description.ilike(like),
            )
        )

    statement = statement.order_by(
        Department.name.asc(),
        Department.id.asc(),
    )

    return list(
        db.session.execute(
            statement
        ).scalars()
    )


@transactional
def create_department(
    clinic_id: int,
    code: str,
    name: str,
    description: str | None = None,
) -> Department:
    clinic = _get_clinic(
        clinic_id,
        for_update=True,
    )

    _ensure_active_clinic(clinic)

    code = _normalize_code(code)
    name = _normalize_name(name)
    description = _normalize_description(
        description
    )

    _ensure_unique_code(
        clinic.id,
        code,
    )

    _ensure_unique_name(
        clinic.id,
        name,
    )

    department = Department(
        clinic_id=clinic.id,
        code=code,
        name=name,
        description=description,
        status=DepartmentStatus.ACTIVE,
    )

    db.session.add(department)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Department",
        entity_id=department.id,
        clinic_id=clinic.id,
        description=(
            f"Department '{department.name}' "
            f"({department.code}) created"
        ),
        new_value={
            "clinic_id": clinic.id,
            "code": department.code,
            "name": department.name,
            "description": department.description,
            "status": department.status.value,
        },
    )

    return department


@transactional
def update_department(
    clinic_id: int,
    department_id: int,
    **fields,
) -> Department:
    clinic = _get_clinic(
        clinic_id,
        for_update=True,
    )

    _ensure_active_clinic(clinic)

    department = _get_department(
        clinic_id=clinic.id,
        department_id=department_id,
        for_update=True,
    )

    allowed_fields = {
        "code",
        "name",
        "description",
    }

    unknown_fields = set(fields) - allowed_fields

    if unknown_fields:
        raise ValidationError(
            "Unsupported department fields: "
            + ", ".join(
                sorted(unknown_fields)
            )
        )

    if not fields:
        return department

    if "code" in fields:
        fields["code"] = _normalize_code(
            fields["code"]
        )

        _ensure_unique_code(
            clinic.id,
            fields["code"],
            exclude_department_id=department.id,
        )

    if "name" in fields:
        fields["name"] = _normalize_name(
            fields["name"]
        )

        _ensure_unique_name(
            clinic.id,
            fields["name"],
            exclude_department_id=department.id,
        )

    if "description" in fields:
        fields["description"] = (
            _normalize_description(
                fields["description"]
            )
        )

    old_value = {}
    new_value = {}

    for key, new_raw in fields.items():
        current = getattr(
            department,
            key,
        )

        if current == new_raw:
            continue

        old_value[key] = current
        new_value[key] = new_raw

        setattr(
            department,
            key,
            new_raw,
        )

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Department",
            entity_id=department.id,
            clinic_id=clinic.id,
            description=(
                f"Department '{department.name}' "
                "updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return department


@transactional
def change_department_status(
    clinic_id: int,
    department_id: int,
    new_status: DepartmentStatus,
) -> Department:
    clinic = _get_clinic(
        clinic_id,
        for_update=True,
    )

    _ensure_active_clinic(clinic)

    new_status = _validate_status(
        new_status
    )

    department = _get_department(
        clinic_id=clinic.id,
        department_id=department_id,
        for_update=True,
    )

    if department.status == new_status:
        return department

    old_status = department.status

    department.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Department",
        entity_id=department.id,
        clinic_id=clinic.id,
        description=(
            f"Department '{department.name}' "
            f"status changed to '{new_status.value}'"
        ),
        old_value={
            "status": old_status.value,
        },
        new_value={
            "status": new_status.value,
        },
    )

    return department