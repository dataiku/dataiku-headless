# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cobuild object links follow Dataiku UI routes without SDK lookups."""

import pytest

from dataiku_mcp.tools.utils.cobuild_links import extract_object_links


@pytest.mark.parametrize(
    ("object_type", "path"),
    [
        ("WEB_APP", "webapps/item_/view"),
        ("RECIPE", "recipes/item/"),
        ("ANALYSIS", "analysis/item/script/"),
        ("DATASET", "datasets/item/explore/"),
        ("DASHBOARD", "dashboards/item_/view/"),
        ("INSIGHT", "dashboards/insights/item_/view"),
        ("AI_AGENT", "savedmodels/item/versions/"),
        ("FINE_TUNED_MODEL", "savedmodels/item/versions/"),
        ("GEN_AI_MODEL", "savedmodels/item/versions/"),
        ("GENAI_EVALUATION_STORE", "genaievaluationstores/item/evaluations/"),
        ("RETRIEVABLE_KNOWLEDGE", "knowledge-bank/item/usage/"),
        ("FLOW_ZONE", "flow/?zoneId=item"),
    ],
)
def test_local_object_routes(object_type, path):
    assert extract_object_links(
        f"Created [an object]({object_type}:item).", "https://example.com", "PROJECT"
    ) == [
        {
            "reference": f"{object_type}:item",
            "url": f"https://example.com/projects/PROJECT/{path}",
        }
    ]


def test_qualified_ids_base_path_escaping_and_duplicate_targets():
    message = (
        "[app](web_app:OTHER.app) and [again](WEB_APP:OTHER.app)\n"
        r"[notebook](JUPYTER_NOTEBOOK:PROJECT.sales \(draft\)/?#)"
    )
    assert extract_object_links(message, "https://example.com/dss/", "PROJECT") == [
        {
            "reference": "WEB_APP:OTHER.app",
            "url": "https://example.com/dss/projects/OTHER/webapps/app_/view",
        },
        {
            "reference": "JUPYTER_NOTEBOOK:PROJECT.sales (draft)/?#",
            "url": "https://example.com/dss/projects/PROJECT/notebooks/jupyter/"
            "sales%20%28draft%29%2F%3F%23/",
        },
    ]


@pytest.mark.parametrize(
    "message",
    [
        "Nothing created.",
        "[external](https://example.org/path)",
        "[unknown](FUTURE_TYPE:PROJECT.item)",
        "[empty](WEB_APP:)",
        "[empty project](WEB_APP:.item)",
        "[empty id](WEB_APP:PROJECT.)",
        "[dot segment](RECIPE:PROJECT...)",
        "[unfinished](WEB_APP:PROJECT.item",
    ],
)
def test_unsupported_or_invalid_references_do_not_invent_links(message):
    assert extract_object_links(message, "https://example.com", "PROJECT") == []
