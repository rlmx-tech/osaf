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
