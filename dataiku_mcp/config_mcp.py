# Copyright 2026 Dataiku
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

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dataiku-mcp")

DKU_MCP_MAX_WORKERS = int(os.environ.get("DKU_MCP_MAX_WORKERS", "4"))
# Bounds parallel blocking Cobuild calls; additional retained turns queue locally.
DKU_MCP_MAX_COBUILD_WORKERS = int(os.environ.get("DKU_MCP_MAX_COBUILD_WORKERS", "4"))
