from app.document_engine.normalization.models.blocks import NormalizedParagraphStyle, NormalizedTableStyle, NormalizedRowStyle, NormalizedCellStyle, NormalizedTableBorder, NormalizedTableWidth
from app.document_engine.normalization.models.inlines import NormalizedTextStyle
from app.document_engine.normalization.models.sections import NormalizedSectionStyle
from app.document_engine.normalization.models.shared import NormalizedMargins

from app.document_engine.enums.enums import ParagraphAlignment, TableBorderStyleEnum, TableCellShading, VerticalAlignment, SectionType, PageOrientation, TableWidthType


DEFAULT_TEXT_STYLE = NormalizedTextStyle(
    bold=False,
    italic=False,
    underline=False,
    font_name="Calibri",
    font_size=22,
    color="000000",
)


DEFAULT_PARAGRAPH_STYLE = NormalizedParagraphStyle(
    alignment=ParagraphAlignment("left"),
    spacing_before=0,
    spacing_after=0,
    indent_left=0,
    indent_right=0,
    keep_next=False,
)


DEFAULT_TABLE_WIDTH = NormalizedTableWidth(
    value=None,
    type=TableWidthType("auto"),
)


DEFAULT_TABLE_MARGINS = NormalizedMargins(
    top=0,
    bottom=0,
    left=108,
    right=108,
)


DEFAULT_TABLE_BORDER = NormalizedTableBorder(
    style=TableBorderStyleEnum("none"),
    size=0,
    color="000000",
)


DEFAULT_TABLE_STYLE = NormalizedTableStyle(
    width=DEFAULT_TABLE_WIDTH,
    autofit=True,
    border_top=DEFAULT_TABLE_BORDER,
    border_left=DEFAULT_TABLE_BORDER,
    border_bottom=DEFAULT_TABLE_BORDER,
    border_right=DEFAULT_TABLE_BORDER,
    border_inside_v=DEFAULT_TABLE_BORDER,
    border_inside_h=DEFAULT_TABLE_BORDER,
    margins=DEFAULT_TABLE_MARGINS,
    column_width=(),
)


DEFAULT_ROW_STYLE = NormalizedRowStyle(
    height=0,
    header=False,
)


DEFAULT_CELL_MARGINS = NormalizedMargins(
    top=0,
    bottom=0,
    left=108,
    right=108,
)


DEFAULT_CELL_STYLE = NormalizedCellStyle(
    shading=TableCellShading("clear"),
    shading_fill="FFFFFF",
    margins=DEFAULT_CELL_MARGINS,
    grid_span=1,
    v_alignment=VerticalAlignment("top"),
    border_top=None,
    border_left=None,
    border_bottom=None,
    border_right=None,
)


DEFAULT_SECTION_MARGINS = NormalizedMargins(
    top=1440,
    bottom=1440,
    left=1440,
    right=1440,
)


DEFAULT_SECTION_STYLE = NormalizedSectionStyle(
    section_type=SectionType("nextPage"),
    page_width=12240,
    page_height=15840,
    orientation=PageOrientation("portrait"),
    margin_header=720,
    margin_footer=720,
    margins=DEFAULT_SECTION_MARGINS,
)