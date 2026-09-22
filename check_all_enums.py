from __future__ import annotations

import enum

import sqlalchemy as sa
from sqlalchemy import inspect

from app import create_app
from app.extensions import db


app = create_app("development")


def get_python_enum_values(enum_type: sa.Enum) -> list[str]:
    return list(enum_type.enums)


with app.app_context():
    engine = db.engine
    metadata = db.metadata
    inspector = inspect(engine)

    app_enums: dict[str, set[str]] = {}

    for table in metadata.tables.values():
        for column in table.columns:
            column_type = column.type

            if not isinstance(column_type, sa.Enum):
                continue

            enum_name = column_type.name

            if not enum_name:
                continue

            values = get_python_enum_values(column_type)

            if enum_name not in app_enums:
                app_enums[enum_name] = set(values)
            else:
                app_enums[enum_name].update(values)

    db_enums: dict[str, set[str]] = {}

    for enum_info in inspector.get_enums(schema="public"):
        db_enums[enum_info["name"]] = set(enum_info["labels"])

    print("=" * 80)
    print("APPLICATION ENUMS")
    print("=" * 80)

    for enum_name in sorted(app_enums):
        values = sorted(app_enums[enum_name])
        print(f"\n{enum_name}")
        for value in values:
            print(f"  {value}")

    print("\n" + "=" * 80)
    print("POSTGRESQL ENUMS")
    print("=" * 80)

    for enum_name in sorted(db_enums):
        values = sorted(db_enums[enum_name])
        print(f"\n{enum_name}")
        for value in values:
            print(f"  {value}")

    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    all_names = sorted(set(app_enums) | set(db_enums))

    problems = False

    for enum_name in all_names:
        app_values = app_enums.get(enum_name)
        db_values = db_enums.get(enum_name)

        if app_values is None:
            problems = True
            print(f"\nEXTRA IN DATABASE: {enum_name}")
            print(f"  Database values: {sorted(db_values)}")
            continue

        if db_values is None:
            problems = True
            print(f"\nMISSING IN DATABASE: {enum_name}")
            print(f"  Application values: {sorted(app_values)}")
            continue

        missing = app_values - db_values
        extra = db_values - app_values

        if not missing and not extra:
            print(f"\nOK: {enum_name}")
            continue

        problems = True

        print(f"\nMISMATCH: {enum_name}")

        if missing:
            print("  Missing from PostgreSQL:")
            for value in sorted(missing):
                print(f"    - {value}")

        if extra:
            print("  Extra in PostgreSQL:")
            for value in sorted(extra):
                print(f"    - {value}")

    print("\n" + "=" * 80)

    if problems:
        print("RESULT: ENUM ALIGNMENT PROBLEMS FOUND")
    else:
        print("RESULT: ALL APPLICATION ENUMS MATCH POSTGRESQL")

    print("=" * 80)