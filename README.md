# NeMo-Agent-Toolkit-schemagate

[schemagate](https://github.com/ashishsinha1602/schemagate) for
[NVIDIA NeMo Agent Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit). A text-to-SQL agent gets only the
tables a question needs, picked from the tables the caller may read. A table the caller can't read is never a
candidate, so it can't reach the prompt.

This package is a third-party plugin, maintained outside the NeMo Agent Toolkit repository.

## What it does

schemagate reflects your database once (table structure only, never rows), indexes it, and for each question
selects a handful of tables and views with hybrid lexical and vector retrieval, then adds the join tables the
question never names by following foreign keys. Objects and columns restricted to roles the caller lacks are
removed before ranking. The result is compact DDL to put in the SQL-writing prompt.

Selection runs locally and calls no model.

On Spider 2.0-lite's public BigQuery and Snowflake schemas, the median saving per database with 50+ tables was
91.1% of the prompt tokens the full schema would take. On small schemas there is little to cut: 8.8% on BIRD's
seven-table databases. The method, the full table and the recall trade-off are in
[schemagate's BENCHMARKS.md](https://github.com/ashishsinha1602/schemagate/blob/main/BENCHMARKS.md#prompt-tokens-on-public-schemas-the-saving-grows-with-the-schema).

## Installation

```bash
uv add nemo-agent-toolkit-schemagate
```

or:

```bash
pip install nemo-agent-toolkit-schemagate
```

Database drivers are not included. Install the one for your database, for example `psycopg[binary]` for
PostgreSQL or `oracledb` for Oracle. SQLite needs nothing.

Check that NeMo Agent Toolkit discovers the plugin:

```bash
nat info components -q schemagate
```

## Registered components

| Kind | `_type` | Tools / use |
| --- | --- | --- |
| Function group | `schemagate` | `<instance>__select`, `<instance>__list_objects` (with the instance named `schemagate`: `schemagate__select`, `schemagate__list_objects`) |
| Retriever | `schemagate` | Native toolkit retriever. One `Document` of DDL per selected table, for `nat_retriever` or `builder.get_retriever` |

Entry point: `nat_schemagate = "nemo_agent_toolkit_schemagate.register"` in the `nat.plugins` group.

`schemagate__select` takes `question` and returns:

- `ddl`: the prompt fragment, compact DDL of the selected tables and views
- `objects`: the names chosen
- `explain`: score and selection reason per object
- `selected`, `total_objects`, `question`

`schemagate__list_objects` returns every table and view the caller may read, with kind, column count and
description.

## Minimal workflow

No database and no API key needed for the tool itself: `database_url: demo` uses schemagate's bundled SQLite
schema (42 tables and views; `hr_compensation` is readable by the `payroll` role only).

```yaml
function_groups:
  schemagate:
    _type: schemagate
    database_url: demo
    top_k: 6

llms:
  my_llm:
    _type: nim
    model_name: meta/llama-3.3-70b-instruct

workflow:
  _type: react_agent
  llm_name: my_llm
  tool_names:
    - schemagate
```

```bash
export NVIDIA_API_KEY=...
nat run --config_file examples/config.yml --input "Which tables do I need for late shipments by carrier?"
```

[`examples/config.yml`](examples/config.yml) is this workflow. [`examples/config_ollama.yml`](examples/config_ollama.yml)
is the same against a local Ollama server, with no key. [`examples/retriever.yml`](examples/retriever.yml) uses
the retriever through the toolkit's `nat_retriever` function.

## Configuration

The same fields apply to the function group and the retriever.

| Field | Default | Description |
| --- | --- | --- |
| `database_url` | `SCHEMAGATE_DATABASE_URL`, then `demo` | SQLAlchemy URL to reflect, or `demo`. Stored as a secret, since a URL can carry a password. |
| `top_k` | `6` | Tables and views selected before foreign-key expansion adds join tables (1 to 50). |
| `principal` | none | Caller identity, namespaced as `<source>:<id>`, for example `okta:jdoe`. |
| `roles` | `[]` | Roles of the caller. A table or column restricted to roles the caller lacks is never selected. |
| `expand_foreign_keys` | `true` | Pull in join tables the question never names. |
| `max_columns` | `40` | Columns shown per table in the DDL. |
| `config_file` | none | A schemagate config file (hints, restrictions, concepts, rules), applied after reflection. |

### Who the caller is

`principal` and `roles` are configuration, set by whoever deploys the workflow, and are deliberately not tool
arguments. If the agent could pass roles, it could pass `payroll` and read what the payroll role may read. One
configured group or retriever serves one caller identity; configure one instance per role you serve:

```yaml
function_groups:
  analyst_schema:
    _type: schemagate
    database_url: ${SCHEMAGATE_DATABASE_URL}
    principal: okta:analyst
    roles: [analyst]
  payroll_schema:
    _type: schemagate
    database_url: ${SCHEMAGATE_DATABASE_URL}
    principal: okta:payroll
    roles: [analyst, payroll]
```

Restrictions come from a schemagate `config_file` or, for the demo, are built in. See
[schemagate's README](https://github.com/ashishsinha1602/schemagate#readme) for restricting by role and reading
grants from the database.

## Supported versions

- NeMo Agent Toolkit (`nvidia-nat-core`) 1.8 and 1.9; the dependency is `>=1.8,<2`.
- schemagate `>=1.15.1,<2`.
- Python 3.11, 3.12 and 3.13.

## Tests

The tests use the bundled demo schema and need no network, database or API key.

```bash
uv sync --extra test
uv run pytest tests/ -v
```

or:

```bash
pip install -e ".[test]"
pytest tests/ -v
```

## Bugs

- Wrong tables selected, a restriction not applied, or a problem in this plugin: open an issue in
  [this repository](https://github.com/ashishsinha1602/NeMo-Agent-Toolkit-schemagate/issues) or in
  [schemagate](https://github.com/ashishsinha1602/schemagate/issues).
- A problem in NeMo Agent Toolkit itself (`nat` CLI, workflow loading, agents): open an issue in
  [NVIDIA/NeMo-Agent-Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues).

Security issues: follow schemagate's [SECURITY.md](https://github.com/ashishsinha1602/schemagate/blob/main/SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
