from lxml.etree import _Element

from app.document_engine.parser.extractors.styles import (
    extract_alignment,
    extract_indent,
    extract_run_style,
)
from app.document_engine.parser.models.styles import (
    Numbering,
    NumberingDefinition,
    NumberingInstance,
    NumberingLevel,
)
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.utils.get_attribute import get_int_attr, get_prop, get_int_prop


def parse_numbering(root: _Element | None) -> Numbering:
    """numbering.xml: list definitions (<w:abstractNum>) and the instances 
    that paragraphs name (<w:num>).
    """

    if root is None:
        return Numbering()

    definitions = []
    for node in root.findall("w:abstractNum", NS):
        definition_id = get_int_attr(node, "abstractNumId")
        if definition_id is None:
            continue

        levels = []
        for lvl in node.findall("w:lvl", NS):
            level = get_int_attr(lvl, "ilvl")
            if level is not None:
                levels.append(_level(lvl, level))

        definitions.append(NumberingDefinition(
            definition_id=definition_id,
            levels=tuple(levels),
        ))

    instances = []
    for node in root.findall("w:num", NS):
        num_id = get_int_attr(node, "numId")
        definition_id = get_int_prop(node, "w:abstractNumId")
        if num_id is not None and definition_id is not None:
            instances.append(NumberingInstance(
                num_id=num_id,
                definition_id=definition_id,
                start_overrides=_start_overrides(node),
            ))

    return Numbering(definitions=tuple(definitions), instances=tuple(instances))


def _level(node: _Element, level: int) -> NumberingLevel:
    """Only what draws the number. pStyle, isLfl, legacy, picture bullets and 
    the level's tab stop are not read.
    """

    left, _, first_line = extract_indent(node.find("w:pPr/w:ind", NS))

    return NumberingLevel(
        level=level,
        start=get_int_prop(node, "w:start"),
        format=get_prop(node, "w:numFmt"),
        text=get_prop(node, "w:lvlText"),
        alignment=extract_alignment(node.find("w:lvlJc", NS)),
        suffix=get_prop(node, "w:suff"),
        indent_left=left,
        indent_first_line=first_line,
        style=extract_run_style(node.find("w:rPr", NS)),
    )


def _start_overrides(num: _Element) -> tuple[tuple[int, int], ...]:
    """<w:lvlOverride><w:startOverride/> restarts a level. A whole 
    replacement <w:lvl> inside the override is not read.
    """

    overrides = []
    for override in num.findall("w:lvlOverride", NS):
        level = get_int_attr(override, "ilvl")
        start = get_int_prop(override, "w:startOverride")
        if level is not None and start is not None:
            overrides.append((level, start))

    return tuple(overrides)