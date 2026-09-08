"""Relevance matching must respect word boundaries.

The gate favors recall on purpose, but naive substring matching is not recall —
it is noise. Species names are short and common as fragments: "mako" appears
inside the Reddit username /u/makoextinct and inside the Maori bird name
korimako, and a real r/newzealand bird-of-the-year post was captured because of
exactly that.
"""

import pytest

from collector.relevance import is_shark_relevant


class TestSubstringFalsePositives:
    @pytest.mark.parametrize(
        ("title", "content"),
        [
            # The real captured item, verbatim from production.
            ("vote putangitangi for bird of thr year", "submitted by /u/makoextinct"),
            ("Bird of the year results", "the korimako came second"),
            ("Local news", "Thresherman Road closed for repairs"),
            ("Sports", "the blacktipped pen ran out of ink"),
        ],
    )
    def test_species_name_inside_another_word_is_not_a_match(self, title, content):
        assert is_shark_relevant(title, content) is False

    def test_unrelated_text_is_still_not_a_match(self):
        assert is_shark_relevant("Council extends pier budget", "construction news") is False


class TestGenuineMentionsStillMatch:
    @pytest.mark.parametrize(
        ("title", "content"),
        [
            ("Mako sighted off the coast", ""),
            ("Two makos tagged by researchers", ""),
            ("Shark spotted at the beach", ""),
            ("Sharks are returning to the bay", ""),
            ("A shark's tooth was recovered", ""),
            ("Great white breaches near boat", ""),
            ("Wobbegong bites diver", ""),
            ("", "a thresher was caught on camera"),
            ("Shark-infested waters closed", ""),
            ("SHARK ATTACK REPORTED", ""),
        ],
    )
    def test_real_mentions_are_kept(self, title, content):
        assert is_shark_relevant(title, content) is True


class TestTrustedSourceTerms:
    def test_trusted_source_incident_word_still_matches(self):
        assert is_shark_relevant(
            "Matawan River Attacks Revisited", "", trusted_shark_source=True
        ) is True

    def test_trusted_source_terms_also_respect_boundaries(self):
        # "bite" inside "arbiter" must not qualify a trusted-source item.
        assert is_shark_relevant(
            "The arbiter ruled on the dispute", "", trusted_shark_source=True
        ) is False

    def test_untrusted_source_does_not_get_incident_terms(self):
        assert is_shark_relevant("Bear attack in the woods", "") is False
