# app/bootstrap.py
"""
Idempotent bootstrap for ExpenX.

- Ensures init_db() is invoked only once per process.
- Runs optional schema repair only for SQLite (safe).
- Calls seed_default_accounts() if available, but guarded against errors.
"""

from typing import List, Tuple
import importlib
import traceback

# Import db helpers lazily to avoid circular import at module import time
def _get_db_objects():
    # Import here to avoid circular imports when modules import bootstrap at top-level
    from app.db import init_db, engine, Base  # type: ignore
    return init_db, engine, Base

_BOOTSTRAP_RAN = False

def bootstrap(auto_repair_safe: bool = False) -> List[Tuple[str, int]]:
    """
    Run safe, idempotent bootstrap.
    - auto_repair_safe: if True, attempt schema repair where supported (SQLite only).
    Returns list of created default accounts (name, id) if seeding ran, otherwise [].
    """
    global _BOOTSTRAP_RAN
    if _BOOTSTRAP_RAN:
        return []

    print("Running bootstrap...")

    created_accounts = []

    try:
        init_db, engine, Base = _get_db_objects()

        # Initialize DB metadata (this is cheap and safe to call once)
        # NOTE: init_db implementation should be streamlit-safe and idempotent.
        try:
            # prefer explicit flag to avoid heavy repairs by default
            init_db(auto_repair_safe=False)
        except TypeError:
            # backward-compat: some init_db variants may not accept argument
            init_db()

        # Optional: run schema validator/repair only when requested and only on SQLite
        try:
            if auto_repair_safe and engine.dialect.name == "sqlite":
                # import schema validator and run it with correct signature
                from app.schema_validator import validate_and_repair_schema
                validate_and_repair_schema(engine, Base.metadata, auto_repair=True)
            else:
                if auto_repair_safe:
                    print("[DB] Auto-repair requested but skipped (not sqlite).")
        except Exception as ex:
            # Log but do not raise — don't break bootstrap flow for optional repair.
            print("[DB] WARNING: optional schema repair failed:", ex)
            traceback.print_exc()

        # Seed default accounts (if function available). Use lazy import to avoid circular imports.
        try:
            # Seed helper might live in app.finance or app.db depending on your project structure.
            # Try common locations; if not found, skip gracefully.
            try:
                from app.finance import seed_default_accounts  # type: ignore
            except Exception:
                # fallback location
                try:
                    from app.db import seed_default_accounts  # type: ignore
                except Exception:
                    seed_default_accounts = None

            if seed_default_accounts:
                try:
                    created_accounts = seed_default_accounts() or []
                    if created_accounts:
                        print("Default accounts created:", created_accounts)
                except Exception as se:
                    print("[DB] WARNING: seed_default_accounts failed:", se)
                    traceback.print_exc()
        except Exception as ex:
            print("[DB] WARNING: seeding step failed:", ex)
            traceback.print_exc()

    except Exception as e:
        # Fatal in bootstrap: print and re-raise so app.py can catch and show to user
        print("Bootstrap fatal error:", e)
        traceback.print_exc()
        raise

    _BOOTSTRAP_RAN = True
    print("Bootstrap complete.")
    return created_accounts
