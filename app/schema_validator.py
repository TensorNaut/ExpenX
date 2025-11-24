# app/schema_validator.py
"""
Schema validator & auto-repair for ExpenX (SQLite + SQLAlchemy).

Usage:
  - import validate_and_repair_schema and call it with (engine, Base.metadata)
  - or use the CLI scripts/run_schema_check.py to run manually.

Design:
  - Compares SQLAlchemy model tables & columns (metadata) vs actual DB schema.
  - For missing columns -> attempts ALTER TABLE ADD COLUMN with safe SQLite type mapping.
  - For type mismatches -> attempts safe table rebuild:
      1) create new table with correct schema
      2) copy columns that exist in both tables
      3) drop old table and rename new one
  - Always creates a timestamped backup before destructive operations.
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger("schema_validator")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(handler)

# Path to DB used by your project
DB_PATH = Path("data/expenses.db")
BACKUP_DIR = Path("data/db_backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Map SQLAlchemy/SQL types to SQLite column type strings
_TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'SMALLINT': 'INTEGER',
    'BIGINT': 'INTEGER',
    'FLOAT': 'REAL',
    'NUMERIC': 'REAL',
    'DECIMAL': 'REAL',
    'REAL': 'REAL',
    'VARCHAR': 'TEXT',
    'TEXT': 'TEXT',
    'STRING': 'TEXT',
    'DATE': 'DATE',
    'DATETIME': 'DATETIME',
    'BOOLEAN': 'INTEGER'
}

def _sqlite_type_from_col(col):
    """
    Accepts SQLAlchemy ColumnClause (or .type) and returns a safe SQLite type string.
    The function will attempt to use .__class__.__name__ mapping, fallback to TEXT.
    """
    try:
        typ = getattr(col, 'type', col).__class__.__name__.upper()
        # basic normalization
        for key in _TYPE_MAP:
            if key in typ:
                return _TYPE_MAP[key]
    except Exception:
        pass
    # fallback: if column has a .type.compile() that contains TEXT/REAL/INTEGER use it
    try:
        compiled = str(col.type).upper()
        for key in _TYPE_MAP:
            if key in compiled:
                return _TYPE_MAP[key]
    except Exception:
        pass
    return "TEXT"

def _backup_db():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{DB_PATH.name}.bak.{ts}"
    shutil.copy2(DB_PATH, dest)
    logger.info(f"Database backup created: {dest}")
    return dest

def _get_db_tables(conn: sqlite3.Connection) -> Dict[str, List[Tuple]]:
    """
    Returns dict: table_name -> list of PRAGMA table_info rows
    Each row is (cid, name, type, notnull, dflt_value, pk)
    """
    cur = conn.cursor()
    tables = {}
    for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        tname = row[0]
        rows = cur.execute(f"PRAGMA table_info('{tname}')").fetchall()
        tables[tname] = rows
    return tables

def _col_info_from_pragma_row(row):
    # row -> (cid, name, type, notnull, dflt_value, pk)
    return {'name': row[1], 'type': (row[2] or "").upper(), 'notnull': bool(row[3]), 'default': row[4], 'pk': bool(row[5])}

def _model_columns_from_table(table) -> List[Dict[str, Any]]:
    """
    table is an SQLAlchemy Table object from metadata
    returns list of dicts: name, type, nullable, default
    """
    cols = []
    for c in table.columns:
        type_str = _sqlite_type_from_col(c)
        nullable = c.nullable
        default = None
        # try to extract default
        try:
            if c.server_default is not None:
                default = str(c.server_default.arg)
        except Exception:
            default = None
        cols.append({'name': c.name, 'type': type_str, 'nullable': nullable, 'default': default})
    return cols

def _pragmatize_default(d):
    if d is None:
        return None
    return str(d)

def compare_model_vs_db(engine, metadata) -> Dict[str, Any]:
    """
    Compare SQLAlchemy metadata tables vs DB tables.
    Returns a dict with issues and suggested actions.
    """
    import sqlalchemy
    conn = sqlite3.connect(str(DB_PATH))
    try:
        db_tables = _get_db_tables(conn)
        issues = {}
        for tname, table in metadata.tables.items():
            model_cols = {c['name']: c for c in _model_columns_from_table(table)}
            db_info = db_tables.get(tname)
            if db_info is None:
                issues[tname] = {'status': 'missing_table', 'model_columns': model_cols, 'db_columns': None}
                continue
            db_cols = {row[1]: _col_info_from_pragma_row(row) for row in db_info}
            missing_cols = [c for c in model_cols.keys() if c not in db_cols]
            extra_cols = [c for c in db_cols.keys() if c not in model_cols.keys()]
            mismatches = []
            for cname, mcol in model_cols.items():
                if cname in db_cols:
                    dbcol = db_cols[cname]
                    # compare types loosely
                    mtype = (mcol['type'] or '').upper()
                    dtype = (dbcol['type'] or '').upper()
                    if mtype and dtype and (mtype not in dtype and dtype not in mtype):
                        mismatches.append({'column': cname, 'model_type': mtype, 'db_type': dtype})
            issues[tname] = {'status': 'ok' if not (missing_cols or extra_cols or mismatches) else 'mismatch',
                             'missing_columns': missing_cols,
                             'extra_columns': extra_cols,
                             'type_mismatches': mismatches,
                             'model_columns': model_cols,
                             'db_columns': {k: v for k, v in db_cols.items()}}
        return issues
    finally:
        conn.close()

def safe_add_column(conn: sqlite3.Connection, table: str, col_def_sql: str):
    """
    Add a column using ALTER TABLE ... ADD COLUMN.
    col_def_sql should be e.g. "kind TEXT DEFAULT 'bank'"
    """
    sql = f"ALTER TABLE {table} ADD COLUMN {col_def_sql}"
    logger.info(f"Executing: {sql}")
    conn.execute(sql)
    conn.commit()

def rebuild_table_with_model(conn: sqlite3.Connection, metadata_table, model_cols: List[Dict[str, Any]]):
    """
    Rebuild the specified table from metadata_table:
    - Create a temp table with correct schema (name: {table}_new)
    - Copy overlapping columns from old table to new table
    - Drop old table, rename new table
    """
    tname = metadata_table.name
    tmp = f"{tname}__new"
    cur = conn.cursor()

    # Build CREATE TABLE statement from SQLAlchemy metadata column info
    col_defs = []
    pk_cols = []
    for c in metadata_table.columns:
        col_type = _sqlite_type_from_col(c)
        nullable = '' if c.nullable else ' NOT NULL'
        default = ''
        if getattr(c, 'server_default', None) is not None:
            default = f" DEFAULT ({c.server_default.arg})"
        col_defs.append(f"{c.name} {col_type}{nullable}{default}")
        if c.primary_key:
            pk_cols.append(c.name)
    if pk_cols:
        pk_sql = f", PRIMARY KEY ({', '.join(pk_cols)})"
    else:
        pk_sql = ""
    create_sql = f"CREATE TABLE {tmp} ({', '.join(col_defs)}{pk_sql});"
    logger.info("Creating new table with SQL: %s", create_sql)
    cur.execute(create_sql)

    # copy overlapping columns
    old_cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{tname}')").fetchall()]
    common = [c.name for c in metadata_table.columns if c.name in old_cols]
    if common:
        cols_csv = ", ".join(common)
        copy_sql = f"INSERT INTO {tmp} ({cols_csv}) SELECT {cols_csv} FROM {tname};"
        logger.info("Copying data for columns: %s", common)
        cur.execute(copy_sql)
    else:
        logger.info("No overlapping columns to copy for table %s — new table starts empty.", tname)

    # drop old and rename
    logger.info("Dropping old table %s and renaming %s -> %s", tname, tmp, tname)
    cur.execute(f"DROP TABLE {tname}")
    cur.execute(f"ALTER TABLE {tmp} RENAME TO {tname}")
    conn.commit()

def validate_and_repair_schema(engine, metadata, auto_repair: bool = False) -> Dict[str, Any]:
    """
    Main entrypoint.
    engine: SQLAlchemy engine
    metadata: Base.metadata
    auto_repair: if True, attempt automatic repairs for missing columns & safe rebuilds
    Returns a report dict
    """
    logger.info("Starting schema validation...")
    # report initial comparison
    report = compare_model_vs_db(engine, metadata)

    # If no issues, return
    problems = {t: v for t, v in report.items() if v['status'] != 'ok'}
    if not problems:
        logger.info("No schema problems detected.")
        return report

    logger.warning("Schema problems detected in %d table(s): %s", len(problems), list(problems.keys()))

    if not auto_repair:
        logger.info("Auto-repair not enabled. Returning report without changes.")
        return report

    logger.info("Auto-repair enabled. Backing up DB first...")
    _backup_db()

    # Start repairs
    conn = sqlite3.connect(str(DB_PATH))
    try:
        for tname, info in problems.items():
            status = info['status']
            if status == 'missing_table':
                # create table from metadata
                logger.info("Table '%s' missing: creating from model.", tname)
                metadata.tables[tname].create(bind=engine, checkfirst=True)
                continue

            # missing columns -> try ALTER TABLE ADD COLUMN with default where possible
            missing = info.get('missing_columns') or []
            if missing:
                for colname in missing:
                    mcol = info['model_columns'][colname]
                    col_type = mcol['type']
                    default = mcol.get('default')
                    nullable = mcol.get('nullable', True)
                    default_sql = ""
                    if default is not None:
                        default_sql = f" DEFAULT {default}"
                    # If not nullable and no default -> make default NULL (can't enforce NOT NULL without rebuild)
                    notnull_sql = "" if nullable else ""
                    col_def = f"{colname} {col_type}{notnull_sql}{default_sql}"
                    try:
                        safe_add_column(conn, tname, col_def)
                        logger.info("Added missing column %s to %s", colname, tname)
                    except Exception as ex:
                        logger.exception("Failed to add column %s to %s via ALTER TABLE: %s", colname, tname, ex)
                        # fallback: rebuild table
                        logger.info("Falling back to full rebuild for table %s", tname)
                        rebuild_table_with_model(conn, metadata.tables[tname], metadata.tables[tname].columns)
                        break

            # For type mismatches -> rebuild the table to guarantee correctness
            mismatches = info.get('type_mismatches') or []
            if mismatches:
                logger.info("Type mismatches in %s: %s", tname, mismatches)
                try:
                    rebuild_table_with_model(conn, metadata.tables[tname], metadata.tables[tname].columns)
                    logger.info("Rebuilt table %s to fix type mismatches", tname)
                except Exception as ex:
                    logger.exception("Failed to rebuild table %s: %s", tname, ex)
                    # cannot auto fix further
                    continue

        logger.info("Auto-repair operations complete.")
    finally:
        conn.close()

    # Re-run comparison
    final_report = compare_model_vs_db(engine, metadata)
    logger.info("Final schema validation complete.")
    return final_report
