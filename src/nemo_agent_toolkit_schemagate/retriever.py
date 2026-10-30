# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ashish Sinha.
"""The ``schemagate`` retriever: one Document of DDL per selected table or view.

Use it under ``retrievers:`` and reach it with the toolkit's ``nat_retriever`` function or
``builder.get_retriever``.
"""

from __future__ import annotations

import asyncio

from nat.plugin_api import Builder
from nat.plugin_api import Document
from nat.plugin_api import Retriever
from nat.plugin_api import RetrieverBaseConfig
from nat.plugin_api import RetrieverOutput
from nat.plugin_api import RetrieverProviderInfo
from nat.plugin_api import register_retriever_client
from nat.plugin_api import register_retriever_provider

from . import catalog as sg
from .settings import SchemagateSettings


class SchemagateRetrieverConfig(RetrieverBaseConfig, SchemagateSettings, name="schemagate"):
    """schemagate schema retriever: the tables a question needs, from those the configured caller may read."""


class SchemagateRetriever(Retriever):
    """Native toolkit retriever over a schemagate catalog. The caller is fixed at construction."""

    def __init__(self, catalog, principal, *, top_k: int = 6, expand_foreign_keys: bool = True,
                 max_columns: int = 40) -> None:
        self._catalog = catalog
        self._principal = principal
        self._top_k = top_k
        self._expand_foreign_keys = expand_foreign_keys
        self._max_columns = max_columns

    def _search(self, query: str, top_k: int | None) -> RetrieverOutput:
        sel = self._catalog.select(str(query or "").strip()[:sg.MAX_QUESTION_CHARS],
                                   top_k=sg.clamp_top_k(top_k or self._top_k),
                                   principal=self._principal,
                                   expand_fks=self._expand_foreign_keys)
        return RetrieverOutput(results=[
            Document(page_content=h.doc.render_ddl(self._max_columns, principal=self._principal, question=sel.question),
                     metadata={
                         "name": h.doc.qname,
                         "kind": h.doc.kind,
                         "score": round(h.score, 4),
                         "reason": h.reason,
                         "columns": len(h.doc.columns),
                     },
                     document_id=h.doc.qname) for h in sel.hits
        ])

    async def search(self, query: str, **kwargs) -> RetrieverOutput:
        """``top_k`` may be passed to override the configured value. Other keyword arguments are ignored;
        in particular there is no way to change the caller from here."""
        return await asyncio.to_thread(self._search, query, kwargs.get("top_k"))


@register_retriever_provider(config_type=SchemagateRetrieverConfig)
async def schemagate_retriever_provider(config: SchemagateRetrieverConfig, _builder: Builder):
    yield RetrieverProviderInfo(config=config,
                                description="schemagate: identity-scoped schema selection for text-to-SQL")


@register_retriever_client(config_type=SchemagateRetrieverConfig, wrapper_type=None)
async def schemagate_retriever_client(config: SchemagateRetrieverConfig, _builder: Builder):
    url = sg.resolve_url(config.database_url.get_secret_value())
    catalog = await asyncio.to_thread(sg.build_catalog, url, config.config_file)
    yield SchemagateRetriever(catalog,
                              sg.make_principal(config.principal, config.roles),
                              top_k=config.top_k,
                              expand_foreign_keys=config.expand_foreign_keys,
                              max_columns=config.max_columns)
