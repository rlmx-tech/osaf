"""Gate 1: cheap keyword screen for shark-relevance.

Favors recall — the whole point of the capture layer is to stop missing items.
Precision is handled downstream by the AI event gate (and SP2 feed tabs).

Recall-favoring is not the same as matching anywhere in the string, though.
Species names are short and common as fragments, so a plain substring test
matches inside unrelated words: "mako" occurs in the Reddit username
/u/makoextinct and in the Maori bird name korimako, which is how an
r/newzealand bird-of-the-year post ended up in the feed. Terms are therefore
matched on word boundaries, with plural and possessive forms allowed so
"sharks" and "a shark's tooth" still count.
"""

import re

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

# Suffixes allowed on a match so ordinary inflections still count. Kept
# deliberately short: this is about "shark" vs "sharks", not stemming.
_INFLECTIONS = r"(?:'s|s|es)?"


def _compile_terms(terms: frozenset[str]) -> re.Pattern[str]:
    """Build one alternation matching any term as a whole word.

    Longest first so that a more specific term wins the alternation — without
    it, "blacktip" could match ahead of "blacktip reef" and change which term
    is credited. Behaviour is the same either way here, but the ordering keeps
    the pattern honest if a caller ever needs to know which term hit.
    """
    ordered = sorted(terms, key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in ordered)
    return re.compile(rf"\b(?:{alternation}){_INFLECTIONS}\b", re.IGNORECASE)


_SHARK_PATTERN = _compile_terms(SHARK_RELEVANCE_TERMS)
_TRUSTED_INCIDENT_PATTERN = _compile_terms(TRUSTED_SOURCE_INCIDENT_TERMS)


def is_shark_relevant(
    title: str,
    content: str,
    *,
    trusted_shark_source: bool = False,
) -> bool:
    """True if the text plausibly concerns a shark (recall-favoring)."""
    text = f"{title or ''} {content or ''}"
    if _SHARK_PATTERN.search(text):
        return True
    return bool(trusted_shark_source and _TRUSTED_INCIDENT_PATTERN.search(text))
