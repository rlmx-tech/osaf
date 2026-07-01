from app.services.llm import _parse_json_response


def test_parse_plain_json():
    assert _parse_json_response('{"groups": [["A", "B"]]}') == {"groups": [["A", "B"]]}


def test_parse_markdown_fenced():
    txt = "Here you go:\n```json\n{\"groups\": []}\n```\n"
    assert _parse_json_response(txt) == {"groups": []}


def test_parse_embedded_braces():
    assert _parse_json_response('noise {"groups": [["X"]]} trailing') == {"groups": [["X"]]}


def test_parse_garbage_returns_none():
    assert _parse_json_response("not json at all") is None
