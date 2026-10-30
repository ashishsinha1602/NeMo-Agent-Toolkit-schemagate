# SPDX-License-Identifier: Apache-2.0
"""Loader smoke tests: the toolkit discovers the plugin, YAML selects it, and the tools and retriever run.

Everything runs on schemagate's bundled demo schema. No network, database or API key.
"""

from importlib.metadata import entry_points

import pytest
from nat.builder.workflow_builder import WorkflowBuilder
from nat.cli.type_registry import GlobalTypeRegistry
from nat.data_models.config import Config
from nat.plugin_api import RetrieverOutput
from nat.runtime.loader import PluginTypes
from nat.runtime.loader import discover_and_register_plugins
from nat.test.tool_test_runner import ToolTestRunner
from pydantic import ValidationError

from nemo_agent_toolkit_schemagate.functions import SchemagateFunctionGroupConfig
from nemo_agent_toolkit_schemagate.retriever import SchemagateRetriever
from nemo_agent_toolkit_schemagate.retriever import SchemagateRetrieverConfig

QUESTION = "salary and pay grade by employee"


def test_entry_point_is_declared():
    (entry_point, ) = [ep for ep in entry_points(group="nat.plugins") if ep.name == "nat_schemagate"]
    assert entry_point.value == "nemo_agent_toolkit_schemagate.register"
    entry_point.load()


def test_toolkit_discovers_the_function_group_and_retriever():
    discover_and_register_plugins(PluginTypes.ALL)
    registry = GlobalTypeRegistry.get()
    assert registry.get_function_group(SchemagateFunctionGroupConfig).local_name == "schemagate"
    assert registry.get_retriever_provider(SchemagateRetrieverConfig).local_name == "schemagate"
    assert registry.get_retriever_client(SchemagateRetrieverConfig, None) is not None


def test_yaml_config_selects_schemagate():
    discover_and_register_plugins(PluginTypes.ALL)
    config = Config.model_validate({
        "function_groups": {"schemagate": {"_type": "schemagate", "database_url": "demo", "top_k": 4}},
        "retrievers": {"schema": {"_type": "schemagate", "roles": ["payroll"]}},
        "workflow": {"_type": "test_echo"},
    })
    group = config.function_groups["schemagate"]
    assert isinstance(group, SchemagateFunctionGroupConfig)
    assert group.top_k == 4 and group.principal is None and group.roles == []
    assert isinstance(config.retrievers["schema"], SchemagateRetrieverConfig)


@pytest.mark.parametrize("field", [{"top_k": 0}, {"top_k": 51}, {"max_columns": 0}])
def test_invalid_config_is_rejected(field):
    with pytest.raises(ValidationError):
        SchemagateFunctionGroupConfig(**field)


def test_database_url_is_secret():
    config = SchemagateFunctionGroupConfig(database_url="postgresql://u:hunter2@db/app")
    # Masked wherever the config is printed or logged. (SerializableSecretStr still dumps the value,
    # by the toolkit's design, so a config can be written back out.)
    assert "hunter2" not in repr(config)
    assert "hunter2" not in str(config)
    assert config.database_url.get_secret_value().endswith("@db/app")


async def test_function_group_exposes_two_tools():
    names = await ToolTestRunner().test_function_group(config_type=SchemagateFunctionGroupConfig,
                                                       config_params={"database_url": "demo"})
    assert {n.split("__")[-1] for n in names} == {"select", "list_objects"}
    assert all("__" in n for n in names)


@pytest.mark.parametrize("roles, visible", [([], False), (["payroll"], True)])
async def test_select_tool_is_scoped_to_the_configured_caller(roles, visible):
    out = await ToolTestRunner().test_function_group_tool(
        config_type=SchemagateFunctionGroupConfig,
        function_name="select",
        config_params={"database_url": "demo", "principal": "okta:x", "roles": roles},
        input_kwargs={"question": QUESTION},
    )
    assert ("hr_compensation" in out["ddl"]) is visible
    assert out["selected"] == len(out["objects"]) < out["total_objects"]


async def test_list_objects_tool():
    out = await ToolTestRunner().test_function_group_tool(config_type=SchemagateFunctionGroupConfig,
                                                          function_name="list_objects",
                                                          config_params={"database_url": "demo"})
    names = {o["name"] for o in out["objects"]}
    assert out["count"] == len(names) and "main.hr_compensation" not in names
    hr = await ToolTestRunner().test_function_group_tool(config_type=SchemagateFunctionGroupConfig,
                                                         function_name="list_objects",
                                                         config_params={"database_url": "demo"},
                                                         input_data="hr_")
    assert hr["count"] >= 1 and all("hr_" in o["name"] for o in hr["objects"])
    assert "main.hr_compensation" not in {o["name"] for o in hr["objects"]}  # a filter cannot widen access


async def test_the_select_tool_takes_no_role_argument():
    """The caller is configuration. An agent must not be able to pass itself a role."""
    async with WorkflowBuilder() as builder:
        await builder.add_function_group("schemagate", SchemagateFunctionGroupConfig(database_url="demo"))
        group = await builder.get_function_group("schemagate")
        functions = await group.get_accessible_functions()
    assert set(functions) == {"schemagate__select", "schemagate__list_objects"}
    assert set(functions["schemagate__select"].input_schema.model_fields) == {"question"}
    assert set(functions["schemagate__list_objects"].input_schema.model_fields) == {"name_filter"}


@pytest.mark.parametrize("roles, visible", [([], False), (["payroll"], True)])
async def test_retriever_through_the_builder(roles, visible):
    async with WorkflowBuilder() as builder:
        await builder.add_retriever("schema", SchemagateRetrieverConfig(database_url="demo", roles=roles, top_k=6))
        retriever = await builder.get_retriever("schema")
        out = await retriever.search(QUESTION, top_k=6, roles=["payroll"])  # extra kwargs cannot widen access
    assert isinstance(retriever, SchemagateRetriever)
    assert isinstance(out, RetrieverOutput) and len(out) > 0
    assert all(d.page_content and d.metadata["name"] == d.document_id for d in out.results)
    assert any(d.metadata["name"] == "main.hr_compensation" for d in out.results) is visible
