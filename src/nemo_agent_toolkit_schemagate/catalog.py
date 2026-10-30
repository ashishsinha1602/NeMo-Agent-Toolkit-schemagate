# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ashish Sinha.
"""Build a schemagate catalog and run one selection. No NeMo Agent Toolkit imports here.

Kept separate from the registration code so the provider logic can be unit-tested on its own.
"""

from __future__ import annotations

import os
from typing import Any

from schemagate import Catalog
from schemagate import Principal

#: The value of ``database_url`` that selects schemagate's bundled SQLite demo schema
#: (42 tables and views; ``hr_compensation`` is readable by the ``payroll`` role only).
DEMO = "demo"

#: Environment variable read when ``database_url`` is left empty.
URL_ENV = "SCHEMAGATE_DATABASE_URL"

MAX_TOP_K = 50
MAX_QUESTION_CHARS = 2000


def resolve_url(configured: str | None) -> str:
    """The configured URL, else ``SCHEMAGATE_DATABASE_URL``, else the demo schema."""
    url = (configured or "").strip() or os.environ.get(URL_ENV, "").strip()
    return url or DEMO


def build_catalog(url: str, config_file: str | None = None) -> Catalog:
    """Reflect the database once and index it. Reads table structure only, never rows.

    ``config_file`` is a schemagate YAML or JSON config (hints, restrictions, concepts, rules),
    applied after reflection exactly as ``schemagate serve --config`` applies it.
    """
    if url == DEMO:
        from schemagate.demo_schema import demo_catalog

        catalog = demo_catalog(name="demo")
    else:
        from schemagate.introspect import engine_from_url

        engine = engine_from_url(url, pool_pre_ping=True)
        try:
            catalog = Catalog().bootstrap(engine)
        finally:
            engine.dispose()  # the index is in memory; hold no connection open
    if config_file:
        from schemagate import config as sg_config

        sg_config.apply(catalog, sg_config.load(config_file))
    return catalog


def make_principal(subject: str | None, roles: list[str] | None) -> Principal | None:
    """The caller the selection is scoped to, or None for an anonymous caller.

    Roles without a subject are given the subject ``nat:anonymous`` so a role-only
    configuration still scopes the selection.
    """
    roles = [r for r in (roles or []) if r and r.strip()]
    if not subject and not roles:
        return None
    return Principal(subject or "nat:anonymous", roles=set(roles))


def clamp_top_k(top_k: int) -> int:
    return max(1, min(int(top_k), MAX_TOP_K))


def select(catalog: Catalog,
           question: str,
           *,
           top_k: int,
           principal: Principal | None,
           expand_foreign_keys: bool = True,
           max_columns: int = 40) -> dict[str, Any]:
    """Pick the tables and views ``question`` needs from those ``principal`` may read.

    Returns the prompt fragment (compact DDL) plus the names chosen and why. An object the
    principal may not read is never a candidate, so it is absent from every field.
    """
    question = str(question or "").strip()[:MAX_QUESTION_CHARS]
    if not question:
        return {"error": "question is empty"}
    sel = catalog.select(question, top_k=clamp_top_k(top_k), principal=principal, expand_fks=expand_foreign_keys)
    return {
        "question": question,
        "selected": len(sel.hits),
        "total_objects": sel.total_objects,
        "objects": sel.table_names,
        "ddl": sel.prompt_fragment(max_columns=max_columns),
        "explain": [{"object": h.doc.qname, "score": round(h.score, 4), "reason": h.reason} for h in sel.hits],
    }


def list_objects(catalog: Catalog, principal: Principal | None, name_filter: str = "") -> dict[str, Any]:
    """Every table and view ``principal`` may read: name, kind, column count, description.

    ``name_filter``, if given, keeps only objects whose qualified name contains it (case-insensitive).
    The filter is applied after the visibility check, so it can only narrow the list.
    """
    needle = str(name_filter or "").strip().lower()
    visible = [d for d in catalog.objects() if catalog._visible(d, principal) and needle in d.qname.lower()]
    return {
        "count": len(visible),
        "objects": [{
            "name": d.qname, "kind": d.kind, "columns": len(d.columns), "description": d.hint or d.description
        } for d in visible],
    }
