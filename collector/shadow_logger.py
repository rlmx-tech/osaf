"""Shadow-model diff logging for the extractor soak.

When a shadow Ollama endpoint is configured (COLLECTOR_SHADOW_OLLAMA_URL and
COLLECTOR_SHADOW_OLLAMA_MODEL), the extractor replays every extraction and
verification prompt against the shadow model and logs both responses here.
Nothing in this module may break the primary pipeline: the caller wraps this
call in its own try/except, and a failed write is logged, never raised.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("osaf.shadow")

# /app/data is the collector_data volume: the only writable path in the
# read_only collector container, and it survives image rebuilds and restarts.
DIFF_PATH = "/app/data/shadow_diffs.jsonl"


async def log_shadow_diff(
    source_url: str, prompt_version: str, primary_res: str | None, shadow_res: str | None
) -> None:
    """Record one primary-vs-shadow comparison as a JSONL line."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": source_url,
        "prompt_version": prompt_version,
        "primary": primary_res,
        "shadow": shadow_res,
        "match": primary_res == shadow_res,
    }
    try:
        with open(DIFF_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.warning("shadow: could not write diff entry: %s", exc)