from lxml.etree import _Element

from app.document_engine.parser.models.styles import (
    StyleNode,
    RunStyle,
    ParagraphStyle,
    TableStyle,
    TableBorderStyle,
    Margins,
    TableRowStyle,
    TableCellStyle,
)
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.ooxml_properties.ooxml_properties import (
    OOXMLStyleAttributeNames,
    OOXMLRunAttributeNames,
    OOXMLParagraphAttributeNames,
    OOXMLTableAttributeNames,
    OOXMLTableRowAttributeNames,
    OOXMLTableCellAttributeNames,
)
from app.document_engine.parser.utils.get_attribute import get_attr, get_int_attr


def has_tag(node: _Element | None, tag: str) -> bool | None:
    if node is None:
        return None
    
    found = node.find(tag, NS)
    if found is None:
        return None
    val = get_attr(found, "val")
    return val != "0"


def extract_run_style(run_properties: _Element | None) -> RunStyle:
    if run_properties is None:
        return RunStyle()
    
    font_node = run_properties.find(OOXMLRunAttributeNames.fonts, NS)
    font_name = None
    if font_node is not None:
        font_name = get_attr(font_node, "ascii") or get_attr(font_node, "hAnsi")

    font_size_node = run_properties.find(OOXMLRunAttributeNames.font_size, NS)
    font_size = None
    if font_size_node is not None:
        font_size = get_int_attr(font_size_node, "val")

    color_node = run_properties.find(OOXMLRunAttributeNames.color, NS)
    color = None
    if color_node is not None:
        color = get_attr(color_node, "val")

    return RunStyle(
        bold=has_tag(run_properties, OOXMLRunAttributeNames.bold),
        italic=has_tag(run_properties, OOXMLRunAttributeNames.italic),
        underline=has_tag(run_properties, OOXMLRunAttributeNames.underline),
        font_name=font_name,
        font_size=font_size,
        color=color,
    )


def extract_paragraph_style(paragraph_properties: _Element | None) -> ParagraphStyle:
    if paragraph_properties is None:
        return ParagraphStyle()
    
    alignment_node = paragraph_properties.find(OOXMLParagraphAttributeNames.alignment, NS)
    alignment = None
    if alignment_node is not None:
        alignment = get_attr(alignment_node, "val")

    spacing_node = paragraph_properties.find(OOXMLParagraphAttributeNames.spacing, NS)
    spacing_before = None
    spacing_after = None
    if spacing_node is not None:
        spacing_before = get_int_attr(spacing_node, "before")
        spacing_after = get_int_attr(spacing_node, "after")

    indent_node = paragraph_properties.find(OOXMLParagraphAttributeNames.indent, NS)
    indent_left = None
    indent_right = None
    if indent_node is not None:
        indent_left = get_int_attr(indent_node, "left")
        indent_right = get_int_attr(indent_node, "right")

    return ParagraphStyle(
        alignment=alignment,
        spacing_before=spacing_before,
        spacing_after=spacing_after,
        indent_left=indent_left,
        indent_right=indent_right,
        keep_next=has_tag(paragraph_properties, OOXMLParagraphAttributeNames.keep_next),
    )


def extract_table_border_style(border_node: _Element | None) -> TableBorderStyle | None:
    if border_node is None:
        return None
    
    return TableBorderStyle(
        style=get_attr(border_node, "val"),
        size=get_int_attr(border_node, "sz"),
        color=get_attr(border_node, "color"),
    )


def extract_table_cell_style(cell_properties: _Element | None) -> TableCellStyle:
    if cell_properties is None:
        return TableCellStyle()
    
    shading_node = cell_properties.find(OOXMLTableCellAttributeNames.shading, NS)
    shading = None
    shading_fill = None
    if shading_node is not None:
        shading = get_attr(shading_node, "val")
        shading_fill = get_attr(shading_node, "fill")

    margins_node = cell_properties.find(OOXMLTableCellAttributeNames.margins, NS)
    margins = None
    if margins_node is not None:
        top, bottom, left, right = 0, 0, 0, 0
        top_node = margins_node.find("w:top", NS)
        bottom_node = margins_node.find("w:bottom", NS)
        left_node = margins_node.find("w:left", NS)
        right_node = margins_node.find("w:right", NS)

        if top_node is not None:
            top = get_int_attr(top_node, "w")
        if bottom_node is not None:
            bottom = get_int_attr(bottom_node, "w")
        if left_node is not None:
            left = get_int_attr(left_node, "w")
        if right_node is not None:
            right = get_int_attr(right_node, "w")

        margins = Margins(
            top=top,
            bottom=bottom,
            left=left,
            right=right,
        )

    grid_span_node = cell_properties.find(OOXMLTableCellAttributeNames.grid_span, NS)
    grid_span = None
    if grid_span_node is not None:
        grid_span = get_int_attr(grid_span_node, "val")

    v_alignment_node = cell_properties.find(OOXMLTableCellAttributeNames.v_alignment, NS)
    v_alignment = None
    if v_alignment_node is not None:
        v_alignment = get_attr(v_alignment_node, "val")

    borders_node = cell_properties.find(OOXMLTableCellAttributeNames.borders, NS)
    border_top = border_bottom = border_left = border_right = None
    if borders_node is not None:
        border_top = extract_table_border_style(borders_node.find("w:top", NS))
        border_bottom = extract_table_border_style(borders_node.find("w:bottom", NS))
        border_left = extract_table_border_style(borders_node.find("w:left", NS))
        border_right = extract_table_border_style(borders_node.find("w:right", NS))

    return TableCellStyle(
        shading=shading,
        shading_fill=shading_fill,
        margins=margins,
        grid_span=grid_span,
        v_alignment=v_alignment,
        border_top=border_top,
        border_left=border_left,
        border_bottom=border_bottom,
        border_right=border_right,
    )


def extract_table_row_style(row_properties: _Element | None) -> TableRowStyle:
    if row_properties is None:
        return TableRowStyle()
    
    height_node = row_properties.find(OOXMLTableRowAttributeNames.height, NS)
    height = None
    if height_node is not None:
        height = get_int_attr(height_node, "val")

    return TableRowStyle(
        height=height,
        header=has_tag(row_properties, OOXMLTableRowAttributeNames.header)
    )


def extract_table_style(table_properties: _Element | None) -> TableStyle:
    if table_properties is None:
        return TableStyle()
    
    width_node = table_properties.find(OOXMLTableAttributeNames.width, NS)
    width = None
    width_type = None
    if width_node is not None:
        width = get_int_attr(width_node, "w")
        width_type = get_attr(width_node, "type")

    layout_node = table_properties.find(OOXMLTableAttributeNames.layout, NS)
    autofit = None
    if layout_node is not None:
        layout_type = get_attr(layout_node, "type")
        autofit = layout_type == "autofit"

    borders_node = table_properties.find(OOXMLTableAttributeNames.borders, NS)
    border_top = None
    border_left = None
    border_bottom = None
    border_right = None
    border_inside_v = None
    border_inside_h = None
    if borders_node is not None:
        border_top = extract_table_border_style(
            borders_node.find("w:top", NS)
        )
        border_bottom = extract_table_border_style(
            borders_node.find("w:bottom", NS)
        )
        border_left = extract_table_border_style(
            borders_node.find("w:left", NS)
        )
        border_right = extract_table_border_style(
            borders_node.find("w:right", NS)
        )
        border_inside_v = extract_table_border_style(
            borders_node.find("w:insideV", NS)
        )
        border_inside_h = extract_table_border_style(
            borders_node.find("w:insideH", NS)
        )

    margins_node = table_properties.find(OOXMLTableAttributeNames.margins, NS)
    margins = None
    if margins_node is not None:
        top, bottom, left, right = 0, 0, 0, 0
        top_node = margins_node.find("w:top", NS)
        bottom_node = margins_node.find("w:bottom", NS)
        left_node = margins_node.find("w:left", NS)
        right_node = margins_node.find("w:right", NS)

        if top_node is not None:
            top = get_int_attr(top_node, "w")
        if bottom_node is not None:
            bottom = get_int_attr(bottom_node, "w")
        if left_node is not None:
            left = get_int_attr(left_node, "w")
        if right_node is not None:
            right = get_int_attr(right_node, "w")

        margins = Margins(
            top=top,
            bottom=bottom,
            left=left,
            right=right,
        )

    return TableStyle(
        width=width,
        width_type=width_type,
        autofit=autofit,
        border_top=border_top,
        border_left=border_left,
        border_bottom=border_bottom,
        border_right=border_right,
        border_inside_v=border_inside_v,
        border_inside_h=border_inside_h,
        margins=margins,
    )


def extract_table_grid(table: _Element) -> tuple[int, ...] | None:

    grid_node = table.find(OOXMLTableAttributeNames.grid, NS)
    if grid_node is None:
        return None

    widths: list[int] = []
    for column in grid_node.findall("w:gridCol", NS):
        width = get_int_attr(column, "w")
        if width is None:
            return None     # Partial grid ignored
        widths.append(width)

    return tuple(widths) or None


def parse_styles(styles_root: _Element) -> dict[str, StyleNode]:
    styles: dict[str, StyleNode] = {}

    for style in styles_root.findall(OOXMLStyleAttributeNames.style, NS):
        style_id = get_attr(style, "styleId")
        style_type = get_attr(style, "type")
        if style_id is None or style_type is None:
            continue

        name = None
        name_node = style.find(OOXMLStyleAttributeNames.name, NS)
        if name_node is not None:
            name = get_attr(name_node, "val")

        based_on = None
        based_on_node = style.find(OOXMLStyleAttributeNames.based_on, NS)
        if based_on_node is not None:
            based_on = get_attr(based_on_node, "val")

        run_properties = style.find(OOXMLRunAttributeNames.properties, NS)
        paragraph_properties = style.find(OOXMLParagraphAttributeNames.properties, NS)
        table_properties = style.find(OOXMLTableAttributeNames.properties, NS)

        styles[style_id] = StyleNode(
            style_id=style_id,
            style_type=style_type,
            is_default=get_attr(style, "default") == "1",
            name=name,
            based_on=based_on,
            run_style=extract_run_style(run_properties),
            paragraph_style=extract_paragraph_style(paragraph_properties),
            table_style=extract_table_style(table_properties),
        )

    return styles