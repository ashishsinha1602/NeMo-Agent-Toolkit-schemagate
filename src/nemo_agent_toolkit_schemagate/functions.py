# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ashish Sinha.
"""The ``schemagate`` function group: schema selection as agent tools.

Configured as ``schemagate``, it exposes ``schemagate__select`` and ``schemagate__list_objects``.
"""

from __future__ import annotations

import asyncio
import logging

from nat.plugin_api import Builder
from nat.plugin_api import FunctionGroup
from nat.plugin_api import FunctionGroupBaseConfig
from nat.plugin_api import register_function_group

from . import catalog as sg
from .settings import SchemagateSettings

logger = logging.getLogger(__name__)


class SchemagateFunctionGroupConfig(FunctionGroupBaseConfig, SchemagateSettings, name="schemagate"):
    """schemagate: pick the tables a question needs, from the tables the configured caller may read."""


SELECT_DESCRIPTION = (
    "Start here for any question about the data. Returns the few tables and views the question needs, as "
    "compact DDL to write SQL against. Tables the caller may not read are absent, not ranked low. Input: the "
    "question in plain words. Output: 'ddl' (put it in your SQL prompt), 'objects' (names chosen), 'explain' "
    "(score and reason per object). Reads table structure only, never rows. If the right table is missing, "
    "rephrase the question rather than writing SQL against a table that was not returned.")

LIST_DESCRIPTION = (
    "List every table and view the caller may read, with kind, column count and description. Optional input: "
    "a name filter (substring), empty for all. Returns no DDL and no rows. To answer a question, call the "
    "select tool instead.")


@register_function_group(config_type=SchemagateFunctionGroupConfig)
async def schemagate_function_group(config: SchemagateFunctionGroupConfig, _builder: Builder):
    url = sg.resolve_url(config.database_url.get_secret_value())
    # Reflection is blocking I/O; keep it off the event loop.
    catalog = await asyncio.to_thread(sg.build_catalog, url, config.config_file)
    principal = sg.make_principal(config.principal, config.roles)
    logger.info("schemagate: indexed %d objects", len(catalog))

    group = FunctionGroup(config=config)

    async def select(question: str) -> dict:
        """Pick the tables and views a question needs, scoped to the configured caller."""
        return await asyncio.to_thread(sg.select,
                                       catalog,
                                       question,
                                       top_k=config.top_k,
                                       principal=principal,
                                       expand_foreign_keys=config.expand_foreign_keys,
                                       max_columns=config.max_columns)

    async def list_objects(name_filter: str = "") -> dict:
        """List the tables and views the configured caller may read, optionally only names containing a filter."""
        return sg.list_objects(catalog, principal, name_filter)

    group.add_function("select", select, description=SELECT_DESCRIPTION)
    group.add_function("list_objects", list_objects, description=LIST_DESCRIPTION)

    yield group
