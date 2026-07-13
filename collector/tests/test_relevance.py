import pytest
from collector.relevance import is_shark_relevant


@pytest.mark.parametrize("title,content,expected", [
    ("Great white shark spotted off Bondi", "", True),
    ("Mako breaches near boat", "fishermen stunned", True),   # species w/o "shark"
    ("New documentary about the ocean", "whales and dolphins", False),
    ("Local council budget meeting", "", False),
    ("", "A wobbegong rested on the reef", True),
    (None, "A tiger shark was spotted", True),
])
def test_is_shark_relevant(title, content, expected):
    assert is_shark_relevant(title, content) is expected


@pytest.mark.parametrize("title", [
    "Matawan River Attacks Revisited - Jaws",
    "Recent Australia Attacks Discussion",
    "Swimmer Mauled Near Esperance",
])
def test_trusted_shark_source_accepts_incident_context_without_shark_word(title):
    assert is_shark_relevant(title, "", trusted_shark_source=True)


def test_trusted_shark_source_still_rejects_unrelated_content():
    assert not is_shark_relevant(
        "The US media, why you need to look at everything",
        "",
        trusted_shark_source=True,
    )


def test_untrusted_source_does_not_accept_generic_attack_language():
    assert not is_shark_relevant("Cyber attacks increased this year", "")
