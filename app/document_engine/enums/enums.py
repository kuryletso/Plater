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


class BreakType(StrEnum):
    """Hard breaks that are not text. Soft line break stays a newline in the text."""
    PAGE = "page"
    COLUMN = "column"


class LineSpacingRule(StrEnum):
    AUTO = "auto"               # 240ths of a line
    EXACT = "exact"             # twps
    AT_LEAST = "atLeast"        # twips


class TableAlignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class FieldType(StrEnum):
    """Fields Word recomputes itself at layout, so they are kept as fields."""
    PAGE = "PAGE"
    NUMPAGES = "NUMPAGES"
    SECTIONPAGES = "SECTIONPAGES"


class ScriptPosition(StrEnum):
    """ST_VerticalAlignRun: where a run sits relative to the line."""
    BASELINE = "baseline"
    SUPERSCRIPT = "superscript"
    SUBSCRIPT = "subscript"


class HighlightColor(StrEnum):
    """ST_HighlightColor: Word highlights only in this fixed palette."""
    BLACK = "black"
    WHITE = "white"
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    CYAN = "cyan"
    BLUE = "blue"
    MAGENTA = "magenta"
    DARK_RED = "darkRed"
    DARK_YELLOW = "darkYellow"
    DARK_GREEN = "darkGreen"
    DARK_CYAN = "darkCyan"
    DARK_BLUE = "darkBlue"
    DARK_MAGENTA = "darkMagenta"
    DARK_GRAY = "darkGray"
    LIGHT_GRAY = "lightGray"


class VerticalMerge(StrEnum):
    """ST_Merge: a cell that starts a vertical merge, or one merged into cell above."""
    RESTART = "restart"
    CONTINUE = "continue"


class NumberingSuffix(StrEnum):
    """ST_LevelSuffix: what follow a list number."""
    TAB = "tab"
    SPACE = "space"
    NOTHING = "nothing"