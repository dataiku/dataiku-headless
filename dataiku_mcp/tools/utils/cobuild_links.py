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

"""Resolve Cobuild's inline Markdown object references to Dataiku UI links."""

import re
from urllib.parse import quote

# Dataiku's StateUtils.href.dssObject routes (including extended saved-model types).
# Keep IDs as path segments; no object lookup or display-name slug is required.
_OBJECT_ROUTES = {
    "DATASET": "datasets/{id}/explore/",
    "RECIPE": "recipes/{id}/",
    "ANALYSIS": "analysis/{id}/script/",
    "WEB_APP": "webapps/{id}_/view",
    "DASHBOARD": "dashboards/{id}_/view/",
    "INSIGHT": "dashboards/insights/{id}_/view",
    "SAVED_MODEL": "savedmodels/{id}/versions/",
    "AI_AGENT": "savedmodels/{id}/versions/",
    "FINE_TUNED_MODEL": "savedmodels/{id}/versions/",
    "GEN_AI_MODEL": "savedmodels/{id}/versions/",
    "MODEL_EVALUATION_STORE": "modelevaluationstores/{id}/evaluations/",
    "GENAI_EVALUATION_STORE": "genaievaluationstores/{id}/evaluations/",
    "MANAGED_FOLDER": "managedfolder/{id}/view/",
    "RETRIEVABLE_KNOWLEDGE": "knowledge-bank/{id}/usage/",
    "SCENARIO": "scenarios/{id}/runs/list/",
    "ARTICLE": "wiki/{id}",
    "JUPYTER_NOTEBOOK": "notebooks/jupyter/{id}/",
    "SQL_NOTEBOOK": "notebooks/sql/{id}/",
    "SEARCH_NOTEBOOK": "notebooks/search/{id}/",
    "LABELING_TASK": "labelingtasks/{id}",
    "FLOW_ZONE": "flow/?zoneId={id}",
}
_MARKDOWN_TOKEN = re.compile(
    r"(?P<escape>\\.)"
    r"|^ {0,3}(?P<fence>`{3,}|~{3,})[^\n]*(?:\n|$)"
    r"|(?P<code>`+)"
    r"|(?P<image>!?)\[(?:\\.|[^\[\]\\])*\]"
    r"\((?P<object_type>[A-Z_]+):(?P<object_id>(?:\\.|[^)\\\r\n])+)\)",
    re.IGNORECASE | re.MULTILINE,
)


def _inline_object_references(message: str):
    """Scan supported inline links, skipping escapes, images, and Markdown code."""
    position = 0
    while match := _MARKDOWN_TOKEN.search(message, position):
        position = match.end()
        if match["fence"]:
            fence = match["fence"]
            closing = re.compile(
                r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$",
                re.MULTILINE,
            ).search(message, position)
            position = closing.end() if closing else len(message)
        elif match["code"]:
            # Code spans close only on a run of exactly the opening length.
            closing = re.compile(
                r"(?<!`)" + re.escape(match["code"]) + r"(?!`)"
            ).search(message, position)
            if closing:
                position = closing.end()
        elif match["object_type"] and not match["image"]:
            yield match


def extract_object_links(
    message: str, instance_url: str, project_key: str
) -> list[dict[str, str]]:
    """Return unique resolved links while leaving the original message untouched."""
    links = []
    seen = set()
    for match in _inline_object_references(message):
        object_type = match["object_type"].upper()
        route = _OBJECT_ROUTES.get(object_type)
        if route is None:
            continue
        smart_id = re.sub(r"\\(.)", r"\1", match["object_id"])
        target_project, separator, object_id = smart_id.partition(".")
        if not separator:
            target_project, object_id = project_key, smart_id
        if not target_project or not object_id or object_id in {".", ".."}:
            continue
        url = (
            f"{instance_url.rstrip('/')}/projects/{quote(target_project, safe='')}/"
            + route.format(id=quote(object_id, safe=""))
        )
        if url not in seen:
            links.append({"reference": f"{object_type}:{smart_id}", "url": url})
            seen.add(url)
    return links
