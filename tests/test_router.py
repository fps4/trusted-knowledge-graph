"""Step 3: four routes, and a reason for each."""

from tkg.semantic.router import route


def test_facts_go_to_the_graph():
    assert route("facts", "CQ-02").route == "graph"


def test_an_ambiguous_term_is_refused_with_the_reason():
    r = route("facts", "CQ-09", ambiguous="'active client' has 4 readings")
    assert r.route == "refuse" and "4 readings" in r.reason


def test_passages_are_refused_without_an_index():
    r = route("passages", "CQ-X")
    assert r.route == "refuse" and "index is not available" in r.reason


def test_passages_and_both_route_once_there_is_an_index():
    assert route("passages", "CQ-X", index_available=True).route == "index"
    assert route("both", "CQ-X", index_available=True).route == "hybrid"
