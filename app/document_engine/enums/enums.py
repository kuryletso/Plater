from enum import StrEnum


class HorizontalAlignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class VerticalAlignment(StrEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class HeaderFooterType(StrEnum):
    DEFAULT = "default"
    FIRST = "first"
    EVEN = "even"


class ParagraphAlignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "both"
    DISTRIBUTE = "distribute"


class TableCellShading(StrEnum):
    CLEAR = "clear"
    SOLID = "solid"
    HORZ = "horz"
    VERT = "vert"
    DIAGCROSS = "diagCross"


class TableBorderStyleEnum(StrEnum):
    SINGLE = "single"
    THICK = "thick"
    DOUBLE = "double"
    DASHED = "dashed"
    DOTTED = "dotted"
    DASHDOTSTROKED = "dashDotStroked"
    DOTDASH = "dotDash"
    DOTDOTDASH = "dotDotDash"
    NONE = "none"
    NIL = "nil"


class SectionType(StrEnum):
    NEXTPAGE = "nextPage"
    CONTINUOUS = "continuous"
    EVENPAGE = "evenPage"
    ODDPAGE = "oddPage"
    COLUMN = "column"


class PageOrientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class TableWidthType(StrEnum):
    AUTO = "auto"
    DXA = "dxa"
    PCT = "pct"


class PlaceholderType(StrEnum):
    SCALAR = "scalar"
    TABLE = "table"
    COLUMN = "column"


class MoneySymbolPosition(StrEnum):
    PREFIX = "prefix"
    SUFFIX = "suffix"


class ResolveMode(StrEnum):
    VALUES = "values"
    KEYS = "keys"