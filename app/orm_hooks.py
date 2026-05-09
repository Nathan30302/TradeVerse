"""
ORM integration for partially migrated databases.

Instance __dict__ stripping in before_flush is not enough: SQLAlchemy still
injects Python :class:`Column` defaults into INSERT during compilation when the
primary key is server-generated. We (1) strip collected INSERT/UPDATE param
keys for columns that are absent in the live DB, and (2) temporarily null out
those columns' ``.default`` for the duration of a flush so compiled INSERTs omit
them. Restores on after_flush_postexec and after_rollback.

Note: mutating Table metadata defaults assumes a typical sync Flask request
model; highly concurrent same-process overlapping flushes are not supported.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm import persistence as _persistence

_installed = False
_ORIG_INSERT_COLLECT = _persistence._collect_insert_commands
_ORIG_UPDATE_COLLECT = _persistence._collect_update_commands

_SESSION_STACK_KEY = "_tradeverse_omit_col_default_stack"


def _schema_flags() -> dict[str, Any]:
    try:
        from flask import current_app, has_app_context

        if not has_app_context():
            return {}
    except Exception:
        return {}
    return current_app.extensions.get("tradeverse_schema") or {}


def _omit_sets_for_mapper(mapper) -> frozenset[str] | set[str]:
    tv = _schema_flags()
    try:
        from app.models.trade import Trade
        from app.models.user import User
    except Exception:
        return frozenset()

    cls = getattr(mapper, "class_", None)
    if cls is User:
        return tv.get("omit_user_cols") or frozenset()
    if cls is Trade:
        return tv.get("omit_trade_cols") or frozenset()
    return frozenset()


def _strip_params_keys(params: dict, omit: frozenset | set) -> None:
    if not omit or not params:
        return
    for k in list(params.keys()):
        if k in omit:
            params.pop(k, None)


def _patched_collect_insert_commands(table, states_to_insert, **kw: Any):
    for row in _ORIG_INSERT_COLLECT(table, states_to_insert, **kw):
        state, state_dict, params, mapper, connection, value_params, has_all_pks, has_all_defaults = row
        omit = _omit_sets_for_mapper(mapper)
        _strip_params_keys(params, omit)
        yield (
            state,
            state_dict,
            params,
            mapper,
            connection,
            value_params,
            has_all_pks,
            has_all_defaults,
        )


def _patched_collect_update_commands(
    uowtransaction,
    table,
    states_to_update,
    **kw: Any,
):
    for row in _ORIG_UPDATE_COLLECT(uowtransaction, table, states_to_update, **kw):
        state, state_dict, params, mapper, connection, value_params, has_all_defaults, has_all_pks = row
        omit = _omit_sets_for_mapper(mapper)
        _strip_params_keys(params, omit)
        yield (
            state,
            state_dict,
            params,
            mapper,
            connection,
            value_params,
            has_all_defaults,
            has_all_pks,
        )


def _backup_and_clear_python_defaults(omit_user: set[str], omit_trade: set[str]) -> list[tuple[Any, Any]]:
    backup: list[tuple[Any, Any]] = []
    try:
        from app.models.trade import Trade
        from app.models.user import User
    except Exception:
        return backup

    for name in omit_user:
        col = User.__table__.columns.get(name)
        if col is not None and col.default is not None:
            backup.append((col, col.default))
            col.default = None
    for name in omit_trade:
        col = Trade.__table__.columns.get(name)
        if col is not None and col.default is not None:
            backup.append((col, col.default))
            col.default = None
    return backup


def _restore_python_defaults(session: Session) -> None:
    stack: list[list[tuple[Any, Any]]] | None = session.info.get(_SESSION_STACK_KEY)
    if not stack:
        return
    backup = stack.pop()
    for col, prev in backup:
        col.default = prev


def _restore_all_python_defaults(session: Session) -> None:
    stack: list[list[tuple[Any, Any]]] | None = session.info.get(_SESSION_STACK_KEY)
    while stack:
        backup = stack.pop()
        for col, prev in backup:
            col.default = prev


def install_once() -> None:
    """Register SQLAlchemy hooks (safe to call multiple times — no-op after first)."""

    global _installed
    if _installed:
        return
    _installed = True

    _persistence._collect_insert_commands = _patched_collect_insert_commands
    _persistence._collect_update_commands = _patched_collect_update_commands

    @event.listens_for(Session, "before_flush", propagate=True)
    def _strip_legacy_mapped_attrs(session: Session, flush_context, instances) -> None:
        tv = _schema_flags()
        omit_u = set(tv.get("omit_user_cols") or ())
        omit_t = set(tv.get("omit_trade_cols") or ())
        if omit_u:
            backup = _backup_and_clear_python_defaults(omit_u, omit_t)
            if backup:
                session.info.setdefault(_SESSION_STACK_KEY, []).append(backup)
        elif omit_t:
            backup = _backup_and_clear_python_defaults(set(), omit_t)
            if backup:
                session.info.setdefault(_SESSION_STACK_KEY, []).append(backup)

        if not omit_u and not omit_t:
            return

        try:
            from app.models.trade import Trade
            from app.models.user import User
        except Exception:
            return

        for obj in set(session.new) | set(session.dirty):
            if isinstance(obj, User) and omit_u:
                bucket = getattr(sa_inspect(obj), "dict", None)
                if isinstance(bucket, dict):
                    for col in omit_u:
                        bucket.pop(col, None)
            elif isinstance(obj, Trade) and omit_t:
                bucket = getattr(sa_inspect(obj), "dict", None)
                if isinstance(bucket, dict):
                    for col in omit_t:
                        bucket.pop(col, None)

    @event.listens_for(Session, "after_flush_postexec", propagate=True)
    def _after_flush_restore_defaults(session: Session, flush_context) -> None:
        _restore_python_defaults(session)

    @event.listens_for(Session, "after_rollback", propagate=True)
    def _after_rollback_restore_defaults(session: Session) -> None:
        _restore_all_python_defaults(session)
