"""Gate 1: cheap keyword screen for shark-relevance.

Favors recall — the whole point of the capture layer is to stop missing items.
Precision is handled downstream by the AI event gate (and SP2 feed tabs).
"""

from collector.config import COMMON_TO_SCIENTIFIC

# "shark" plus every species common name (mako, wobbegong, thresher, etc. lack "shark")
SHARK_RELEVANCE_TERMS: frozenset[str] = frozenset(
    {"shark", *(k.lower() for k in COMMON_TO_SCIENTIFIC.keys())}
)


def is_shark_relevant(title: str, content: str) -> bool:
    """True if the text plausibly concerns a shark (recall-favoring)."""
    text = f"{title or ''} {content or ''}".lower()
    return any(term in text for term in SHARK_RELEVANCE_TERMS)
