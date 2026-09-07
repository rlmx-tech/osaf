"""Test configuration for collector unit tests.

The collector's Settings instantiates at import time and validates its own
configuration, so every required value must be present before any collector
module loads:

  - osaf_password has no default at all.
  - ollama_api_key is required whenever ollama_url is remote, and the default
    url (https://ollama.com) is remote. No test makes a real Ollama call; the
    dummy token exists only to satisfy startup validation.
"""

import os

os.environ.setdefault("COLLECTOR_OSAF_PASSWORD", "test-password")
os.environ.setdefault("COLLECTOR_OLLAMA_API_KEY", "test-ollama-key")
