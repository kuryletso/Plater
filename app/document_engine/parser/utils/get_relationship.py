from lxml.etree import _Element
from app.document_engine.parser.namespaces import NS

RELATIONSHIP_NAMESPACE = NS["r"]


def get_relationship_id(node: _Element) -> str | None:
    return node.get(f"{{{RELATIONSHIP_NAMESPACE}}}id")