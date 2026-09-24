from pathlib import Path

from rdflib import Graph

from tkg.ingest import estate as estate_mod
from tkg.ingest import taxonomies


def test_the_generated_vocabulary_is_valid_turtle_and_holds_the_concepts():
    cfg = estate_mod.load_config(Path("/app/config/estate.yaml"))
    graph = Graph().parse(data=taxonomies.build_turtle(cfg), format="turtle")
    subjects = {str(s) for s in graph.subjects()}
    assert "https://lab.fps4.dev/glossary/matter-type/regulatory-investigation" in subjects
    assert "https://lab.fps4.dev/glossary/client-type/fund-manager" in subjects
    assert "https://lab.fps4.dev/id/jurisdiction/NL" in subjects
    assert "https://lab.fps4.dev/id/office/Amsterdam" in subjects
