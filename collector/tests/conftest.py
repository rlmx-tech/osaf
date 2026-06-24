"""Test configuration for collector unit tests.

The collector's Settings instantiates at import time and requires
osaf_password, so provide a dummy value before any collector module loads.
"""

import os

os.environ.setdefault("COLLECTOR_OSAF_PASSWORD", "test-password")
