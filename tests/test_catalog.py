# SPDX-License-Identifier: Apache-2.0
"""Provider logic on schemagate's bundled demo schema. No toolkit runtime, no network, no key."""

import pytest
from schemagate import Principal

from nemo_agent_toolkit_schemagate import catalog as sg


@pytest.fixture(scope="module")
def demo():
    return sg.build_catalog(sg.DEMO)


def test_url_falls_back_to_env_then_demo(monkeypatch):
    monkeypatch.delenv(sg.URL_ENV, raising=False)
    assert sg.resolve_url("") == "demo"
    monkeypatch.setenv(sg.URL_ENV, "sqlite:///x.db")
    assert sg.resolve_url(None) == "sqlite:///x.db"
    assert sg.resolve_url("postgresql://h/db") == "postgresql://h/db"


def test_select_returns_a_prompt_fragment(demo):
    out = sg.select(demo, "late shipments by carrier", top_k=6, principal=None)
    assert "ship_shipment" in out["ddl"]
    assert out["objects"] and out["selected"] == len(out["objects"])
    assert out["selected"] < out["total_objects"]
    assert {"object", "score", "reason"} <= set(out["explain"][0])


def test_top_k_is_respected_without_fk_expansion(demo):
    out = sg.select(demo, "which customers owe us money", top_k=3, principal=None, expand_foreign_keys=False)
    assert out["selected"] == 3


def test_empty_question_is_an_error_not_a_crash(demo):
    assert sg.select(demo, "   ", top_k=6, principal=None) == {"error": "question is empty"}


@pytest.mark.parametrize("roles, visible", [([], False), (["payroll"], True)])
def test_a_table_the_caller_may_not_read_never_reaches_the_prompt(demo, roles, visible):
    who = sg.make_principal("okta:x", roles)
    out = sg.select(demo, "salary and pay grade by employee", top_k=6, principal=who)
    assert ("hr_compensation" in out["ddl"]) is visible
    assert ("main.hr_compensation" in out["objects"]) is visible


def test_list_objects_is_scoped(demo):
    anon = {o["name"] for o in sg.list_objects(demo, None)["objects"]}
    payroll = {o["name"] for o in sg.list_objects(demo, Principal("okta:p", roles={"payroll"}))["objects"]}
    assert "main.hr_compensation" not in anon
    assert payroll - anon == {"main.hr_compensation"}


def test_make_principal():
    assert sg.make_principal(None, []) is None
    assert sg.make_principal(None, ["payroll"]).subject == "nat:anonymous"
    assert sg.make_principal("okta:jdoe", ["a", " "]).roles == frozenset({"a"})
