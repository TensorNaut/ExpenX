# app/schema_validator.py
"""
Safe schema validator and (limited) repair utility.
This module provides a single public function:

    validate_and_repair_schema(engine, metadata, auto_repair=False)

Behavior:
- If engine.dialect.name == "sqlite" and auto_repair==True:
    runs SQLite-focused validation and best-effort repair (existing logic).
- For other backends (Postgres, MySQL, etc.), it performs a lightweight check
  (compares metadata tables vs db tables) and returns a report without attempting
  SQLite-specific repair actions.
- The function returns a dict report summarizing the validation/repair steps.
"""

from typing import Dict, Any
from sqlalchemy import inspect, text
import traceback


def _is_sqlite(engine) -> bool:
    try:
        return engine.dialect.name.lower() == "sqlite"
    except Exception:
        return False


def validate_and_repair_schema(engine, metadata, auto_repair: bool = False) -> Dict[str, Any]:
    """
    Validate database schema against SQLAlchemy metadata.
    - engine: SQLAlchemy Engine
    - metadata: SQLAlchemy MetaData (Base.metadata)
    - auto_repair: only attempts repair for SQLite backend. For Postgres it only reports.
    Returns a dict report.
    """
    report = {"backend": engine.dialect.name if hasattr(engine, "dialect") else "unknown", "issues": [], "actions": []}

    try:
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names())
        model_tables = set(metadata.tables.keys())

        # Tables present in model but missing in DB
        missing_tables = sorted(list(model_tables - db_tables))
        extra_tables = sorted(list(db_tables - model_tables))

        report["missing_tables"] = missing_tables
        report["extra_tables"] = extra_tables

        if _is_sqlite(engine):
            # For SQLite we can attempt the older, table-rebuild style repairs if auto_repair=True
            if auto_repair:
                try:
                    # Simple repair strategy: create missing tables via metadata.create_all
                    metadata.create_all(bind=engine, checkfirst=True)
                    report["actions"].append("created_missing_tables_via_metadata_create_all")
                except Exception as e:
                    report["issues"].append(f"sqlite_repair_failure: {e}")
                    traceback.print_exc()
            else:
                report["note"] = "sqlite detected; auto_repair not requested"
        else:
            # For Postgres and other DBs do not attempt SQLite repairs.
            # Provide a helpful hint about what to do (run alembic migrations).
            if missing_tables:
                report["issues"].append(
                    "missing_tables_detected; do not auto-repair on Postgres. "
                    "Run Alembic migrations or create tables using SQLAlchemy models."
                )
            # We can optionally run metadata.create_all for simple setups, but avoid doing destructive changes here.
            # If user requested auto_repair on non-sqlite, just inform.
            if auto_repair:
                report["actions"].append("auto_repair_requested_but_skipped_for_non_sqlite_backend")

        report["status"] = "ok"
    except Exception as e:
        report["status"] = "error"
        report["error"] = str(e)
        traceback.print_exc()

    return report
