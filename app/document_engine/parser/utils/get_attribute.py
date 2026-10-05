from lxml.etree import _Element

from app.document_engine.parser.namespaces import NS

WORD_NAMESPACE = NS["w"]
ON_OFF_FALSE = frozenset({"0", "false", "off"})


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


def get_bool_attr(node: _Element, attr_name: str) -> bool | None:
    """ST_OnOff attribute, None when absent."""

    value = get_attr(node, attr_name)
    return None if value is None else value not in ON_OFF_FALSE


def get_bool_prop(node: _Element | None, tag: str) -> bool | None:
    """ST_OnOff property element such as <w:b/> or <w:titlePg/>.
    'On' when present without a val. None when absent.
    
    Only for elements whose val is ST_OnOff. <w:u> and <w:highlight> name a style 
    or a color, and 'none' means off there.
    """

    if node is None:
        return None

    found = node.find(tag, NS)
    if found is None:
        return None
    return get_bool_attr(found, "val") is not False


def get_prop(node: _Element | None, tag: str) -> str | None:
    """'w:val' of a property element such as <w:numFmt w:val="decimal"/>. 
    None when absent.
    """

    if node is None:
        return None

    found = node.find(tag, NS)
    return get_attr(found, "val") if found is not None else None


def get_int_prop(node: _Element | None, tag: str) -> int | None:
    if node is None:
        return None

    found = node.find(tag, NS)
    return get_int_attr(found, "val") if found is not None else None