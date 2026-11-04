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

import json
import re

from dataiku_mcp.setup_server import _page


def test_state_embedding_prevents_script_injection_and_round_trips():
    state = {"connections": [{"name": "</script><script>alert(1)</script>"}]}
    page = _page(state, nonce="test-nonce")
    payload = re.search(r'type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(payload) == state
    assert "</script>" not in payload
    assert 'nonce="test-nonce"' in page
