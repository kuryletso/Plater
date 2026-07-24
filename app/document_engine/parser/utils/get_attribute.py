from lxml.etree import _Element

from app.document_engine.parser.namespaces import NS

WORD_NAMESPACE = NS["w"]


def get_attr(node: _Element, attr_name: str) -> str | None:
    return node.get(f"{{{WORD_NAMESPACE}}}{attr_name}")


def get_int_attr(node: _Element, attr_name: str) -> int | None:
    value = get_attr(node, attr_name)
    if value is None:
        return None
    
    try:
        return int(value)
    except ValueError:
        pass

    # Some editors (Google Docs, LibreOffice) emit twips as float "10081.0"
    try:
        return int(float(value))
    except (ValueError, OverflowError):
        return None