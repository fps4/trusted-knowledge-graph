"""The load contract, tested on its own terms.

The rule the whole design rests on — the graph holds assertions and identifiers,
never document content — is a shape, so it can be shown failing rather than
argued for.

Note the full IRIs below: a prefixed name may not carry an unescaped '/', so
`gl:client-type/fund-manager` is not legal Turtle even though it reads well in a
terminal. The real data arrives as N-Quads with absolute IRIs and never meets
this rule.
"""

from pathlib import Path

from rdflib import Graph

from tkg.ingest.loader import validate

ONTOLOGY = Path("/app/ontology/firm.ttl")
SHAPES = Path("/app/ontology/shapes.ttl")

WELL_FORMED = """
@prefix ssf:  <https://lab.fps4.dev/firm/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

<https://lab.fps4.dev/id/client/C-9001> a ssf:Client ;
    ssf:clientRef "C-9001" ;
    rdfs:label "Test Client B.V." ;
    ssf:clientType <https://lab.fps4.dev/glossary/client-type/bank> .

<https://lab.fps4.dev/id/person/P-9001> a ssf:Person ;
    ssf:personRef "P-9001" ;
    ssf:familyName "Tester" ;
    ssf:grade "partner" ;
    ssf:joinedOn "2015-01-01"^^xsd:date .

<https://lab.fps4.dev/id/matter/M-9001> a ssf:Matter ;
    ssf:matterRef "M-9001" ;
    ssf:forClient <https://lab.fps4.dev/id/client/C-9001> ;
    ssf:ledBy <https://lab.fps4.dev/id/person/P-9001> ;
    ssf:matterType <https://lab.fps4.dev/glossary/matter-type/fund-formation> ;
    ssf:inJurisdiction <https://lab.fps4.dev/id/jurisdiction/NL> ;
    ssf:openedOn "2021-01-01"^^xsd:date .
"""


def _validate(turtle: str):
    return validate(Graph().parse(data=turtle, format="turtle"), SHAPES, ONTOLOGY)


def test_a_well_formed_load_conforms():
    result = _validate(WELL_FORMED)
    assert result.conforms, result.report


def test_a_matter_with_two_clients_does_not_land():
    """Two clients on one matter is a conflict-check incident, not a data-quality issue."""
    turtle = WELL_FORMED + """
<https://lab.fps4.dev/id/client/C-9002> a ssf:Client ;
    ssf:clientRef "C-9002" ; rdfs:label "Other B.V." ;
    ssf:clientType <https://lab.fps4.dev/glossary/client-type/bank> .
<https://lab.fps4.dev/id/matter/M-9001>
    ssf:forClient <https://lab.fps4.dev/id/client/C-9002> .
"""
    assert not _validate(turtle).conforms


def test_a_matter_with_no_opening_date_does_not_land():
    turtle = WELL_FORMED.replace(
        'ssf:openedOn "2021-01-01"^^xsd:date .', 'ssf:matterRef "M-9001" .'
    )
    assert not _validate(turtle).conforms


def test_a_null_date_arriving_as_a_string_does_not_land():
    """The defect the load gate caught on its first real run."""
    turtle = WELL_FORMED + """
<https://lab.fps4.dev/id/matter/M-9001> ssf:closedOn "None"^^xsd:date .
"""
    assert not _validate(turtle).conforms


def test_document_content_in_the_graph_does_not_land():
    """The second copy of the DMS fails at the door, not in a code review."""
    prose = "x" * 501
    turtle = WELL_FORMED + f"""
<https://lab.fps4.dev/id/matter/M-9001> rdfs:comment "{prose}" .
"""
    result = _validate(turtle)
    assert not result.conforms
    assert "500 characters" in result.report
