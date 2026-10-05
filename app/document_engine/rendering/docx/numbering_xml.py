from lxml import etree

from app.document_engine.rendering.docx.xml import qn, WORD_NSMAP
from app.document_engine.blueprint.models.document import (
    NumberingBlueprint,
    NumberingLevelBlueprint,
    NumberingRunStyleBlueprint,
)


def build_numbering(numbering: NumberingBlueprint) -> etree._Element:
    """word/numbering.xml . CT_Numbering puts every abstractNum before any num."""

    root = etree.Element(qn("w:numbering"), nsmap=WORD_NSMAP)

    for definition in numbering.definitions:
        abstract = etree.SubElement(root, qn("w:abstractNum"))
        abstract.set(qn("w:abstractNumId"), str(definition.definition_id))
        for level in definition.levels:
            abstract.append(_build_level(level))

    for instance in numbering.instances:
        num = etree.SubElement(root, qn("w:num"))
        num.set(qn("w:numId"), str(instance.num_id))
        etree.SubElement(num, qn("w:abstractNumId"))\
            .set(qn("w:val"), str(instance.definition_id))
        for level, start in instance.start_overrides:
            override = etree.SubElement(num, qn("w:lvlOverride"))
            override.set(qn("w:ilvl"), str(level))
            etree.SubElement(override, qn("w:startOverride")).set(qn("w:val"), str(start))

    return root


def _build_level(level: NumberingLevelBlueprint) -> etree._Element:

    # (!) CT_Lvl order:
    # start > numFmt > suff > lvlText > lvlJc > pPr > rPr

    lvl = etree.Element(qn("w:lvl"))
    lvl.set(qn("w:ilvl"), str(level.level))

    etree.SubElement(lvl, qn("w:start")).set(qn("w:val"), str(level.start))
    etree.SubElement(lvl, qn("w:numFmt")).set(qn("w:val"), str(level.format))
    etree.SubElement(lvl, qn("w:suff")).set(qn("w:val"), str(level.suffix.value))
    etree.SubElement(lvl, qn("w:lvlText")).set(qn("w:val"), str(level.text))
    etree.SubElement(lvl, qn("w:lvlJc")).set(qn("w:val"), str(level.alignment.value))

    ind = etree.SubElement(
        etree.SubElement(lvl, qn("w:pPr")),
        qn("w:ind"),
    )
    ind.set(qn("w:left"), str(level.indent_left))
    if level.indent_first_line < 0:
        ind.set(qn("w:hanging"), str(-level.indent_first_line))
    elif level.indent_first_line > 0:
        ind.set(qn("w:firstLine"), str(level.indent_first_line))


    rpr = _build_level_run_properties(level.style)
    if len(rpr):
        lvl.append(rpr)

    return lvl


def _build_level_run_properties(style: NumberingRunStyleBlueprint) -> etree._Element:
    """Only what the level sets; everything else comes from the paragraph mark."""

    # (!) CT_RPr order: rFonts > b > i > color> sz > u

    rpr = etree.Element(qn("w:rPr"))

    if style.font_name is not None:
        fonts = etree.SubElement(rpr, qn("w:rFonts"))
        fonts.set(qn("w:ascii"), style.font_name)
        fonts.set(qn("w:hAnsi"), style.font_name)
    if style.bold is not None:
        _on_off(rpr, "w:b", style.bold)
    if style.italic is not None:
        _on_off(rpr, "w:i", style.italic)
    if style.color is not None:
        etree.SubElement(rpr, qn("w:color")).set(qn("w:val"), style.color)
    if style.font_size is not None:
        etree.SubElement(rpr, qn("w:sz")).set(qn("w:val"), str(style.font_size))        # half-points
    if style.underline is not None:
        etree.SubElement(rpr, qn("w:u")).set(qn("w:val"), "single" if style.underline else "none")

    return rpr


def _on_off(parent: etree._Element, tag: str, on: bool) -> None:
    """Off has to be written as it switches off what the paragraph mark turns on."""

    element = etree.SubElement(parent, qn(tag))
    if not on:
        element.set(qn("w:val"), "0")