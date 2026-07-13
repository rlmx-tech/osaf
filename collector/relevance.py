"""Gate 1: cheap keyword screen for shark-relevance.

Favors recall — the whole point of the capture layer is to stop missing items.
Precision is handled downstream by the AI event gate (and SP2 feed tabs).
"""

from collector.config import COMMON_TO_SCIENTIFIC

# "shark" plus every species common name (mako, wobbegong, thresher, etc. lack "shark")
SHARK_RELEVANCE_TERMS: frozenset[str] = frozenset(
    {"shark", *(k.lower() for k in COMMON_TO_SCIENTIFIC.keys())}
)

# A curated shark source supplies the missing subject when a headline assumes
# audience context (for example, "Recent Australia Attacks Discussion"). These
# terms are deliberately used only for trusted sources because words such as
# "attack" are far too broad on the open web.
TRUSTED_SOURCE_INCIDENT_TERMS: frozenset[str] = frozenset(
    {
        "attack",
        "bite",
        "bitten",
        "encounter",
        "jaws",
        "mauled",
        "sighting",
        "spotted",
        "beach closure",
    }
)


def is_shark_relevant(
    title: str,
    content: str,
    *,
    trusted_shark_source: bool = False,
) -> bool:
    """True if the text plausibly concerns a shark (recall-favoring)."""
    text = f"{title or ''} {content or ''}".lower()
    if any(term in text for term in SHARK_RELEVANCE_TERMS):
        return True
    return trusted_shark_source and any(
        term in text for term in TRUSTED_SOURCE_INCIDENT_TERMS
    )
