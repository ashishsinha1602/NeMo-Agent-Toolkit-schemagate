# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ashish Sinha.
"""Configuration fields shared by the function group and the retriever."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from nat.plugin_api import SerializableSecretStr


class SchemagateSettings(BaseModel):
    """Where the schema comes from, who the caller is, and how much to select.

    The caller (``principal`` and ``roles``) is set here, by whoever deploys the workflow, and is
    deliberately not a tool argument: an agent that could pass its own roles could grant itself any
    of them. One configured group or retriever serves one caller identity.
    """

    database_url: SerializableSecretStr = Field(
        default_factory=lambda: SerializableSecretStr(""),
        description=("SQLAlchemy database URL to reflect, or 'demo' for schemagate's bundled SQLite schema. "
                     "Falls back to the SCHEMAGATE_DATABASE_URL environment variable, then to 'demo'. "
                     "Kept secret because a URL can carry a password."))
    top_k: int = Field(default=6, ge=1, le=50, description="Number of tables and views to select before "
                       "foreign-key expansion adds required join tables.")
    principal: str | None = Field(default=None,
                                  description="Caller identity, namespaced as '<source>:<id>', for example "
                                  "'okta:jdoe'. Empty means an anonymous caller.")
    roles: list[str] = Field(default_factory=list,
                             description="Roles of the caller. A table restricted to roles the caller lacks is "
                             "never selected.")
    expand_foreign_keys: bool = Field(default=True,
                                      description="Pull in join tables the question never names.")
    max_columns: int = Field(default=40, ge=1, le=500, description="Columns shown per table in the DDL.")
    config_file: str | None = Field(default=None,
                                    description="Optional schemagate config file (hints, restrictions, concepts, "
                                    "rules) applied after reflection.")
