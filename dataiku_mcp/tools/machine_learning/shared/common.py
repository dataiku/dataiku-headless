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

"""Common analysis metadata helpers for machine learning tools."""

from __future__ import annotations


def require_single_ml_task(analysis) -> dict:
    tasks = analysis.list_ml_tasks().get("mlTasks", [])
    if len(tasks) != 1:
        raise ValueError(
            f"Expected exactly 1 ML task in analysis '{analysis.analysis_id}', found {len(tasks)}."
        )
    return tasks[0]


def find_analysis_input_dataset(project, analysis_id: str) -> str | None:
    for analysis_item in project.list_analyses():
        if analysis_item.get("analysisId") == analysis_id:
            return analysis_item.get("inputDataset")
    return None
