from lxml.etree import _Element

from app.document_engine.parser.models.styles import (
    StyleNode,
    RunStyle,
    ParagraphStyle,
    TableStyle,
    TableRowStyle,
    TableCellStyle,
)
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.extractors.styles import (
    extract_run_style,
    extract_paragraph_style,
    extract_table_style,
    extract_table_row_style,
    extract_table_cell_style,
    get_attr,
)
from app.document_engine.utils.overlay_dataclass import overlay_dataclass
from app.document_engine.parser.errors import StyleResolutionError

class StyleResolver:
    def __init__(
            self,
            styles: dict[str, StyleNode],
            doc_defaults: _Element | None,
        ) -> None:

        self.styles = styles
        self._resolved_run_styles: dict[str, RunStyle] = {}
        self._resolved_paragraph_styles: dict[str, ParagraphStyle] = {}
        self._resolved_table_styles: dict[str, TableStyle] = {}
        self._resolved_table_row_styles: dict[str, TableRowStyle] = {}
        self._resolved_table_cell_styles: dict[str, TableCellStyle] = {}

        self.default_run_style = self._parse_default_run_style(doc_defaults)
        self.default_paragraph_style = self._parse_default_paragraph_style(doc_defaults)

        self._default_paragraph_style_id = next(
            (s.style_id for s in styles.values()
            if s.style_type == "paragraph" and s.is_default),
            None
        )

        self.default_table_style = TableStyle(
            autofit=True,
        )

        self.default_table_row_style = TableRowStyle(
            header=False,
        )

        self.default_table_cell_style = TableCellStyle(
            shading="clear",
            v_alignment="top",
        )


    def _parse_default_run_style(self, doc_defaults: _Element | None) -> RunStyle:
        fallback = RunStyle(
            bold=False,
            italic=False,
            underline=False,
            font_name="Calibri",
            font_size=22,
            color="000000",
        )

        if doc_defaults is None:
            return fallback
        
        run_properties = doc_defaults.find("w:rPrDefault/w:rPr", NS)
        if run_properties is None:
            return fallback

        extracted = extract_run_style(run_properties)

        resolved = overlay_dataclass(
            fallback,
            extracted,
        )

        return resolved or fallback
    

    def _parse_default_paragraph_style(self, doc_defaults: _Element | None) -> ParagraphStyle:
        fallback = ParagraphStyle(
            alignment="left",
            spacing_before=0,
            spacing_after=0,
            indent_left=0,
            indent_right=0,
            keep_next=False,
        )

        if doc_defaults is None:
            return fallback
        
        paragraph_properties = doc_defaults.find("w:pPrDefault/w:pPr", NS)
        if paragraph_properties is None:
            return fallback
        
        extracted = extract_paragraph_style(paragraph_properties)

        resolved = overlay_dataclass(
            fallback,
            extracted,
        )

        return resolved or fallback

    def resolve_run_style_by_id(
            self,
            style_id: str | None,
            visited: frozenset[str] = frozenset(),            
        ) -> RunStyle:

        if style_id is None:
            return self.default_run_style
        
        cached = self._resolved_run_styles.get(style_id)
        if cached is not None:
            return cached

        if style_id in visited:
            raise StyleResolutionError(
                f"Circular style dependency detected: {style_id}"
            )
        
        style = self.styles.get(style_id)

        if style is None:
            return self.default_run_style
        
        if style.style_type != "character":
            raise StyleResolutionError(
                f"Invalid style type: {style_id}."
            )
        
        parent_style = self.resolve_run_style_by_id(
            style.based_on,
            visited | {style_id},
        )

        resolved = overlay_dataclass(
            parent_style,
            style.run_style,
        )

        if resolved is None:
            return self.default_run_style
        
        self._resolved_run_styles[style_id] = resolved

        return resolved
    

    def resolve_run_style(
            self,
            run: _Element,
            paragraph_base: RunStyle,
    ) -> RunStyle:
        
        run_properties = run.find("w:rPr", NS)
        if run_properties is None:
            return paragraph_base

        base_style = paragraph_base
        
        style_node = run_properties.find("w:rStyle", NS)
        if style_node is not None:
            char_style = self.resolve_run_style_by_id(
                get_attr(style_node, "val"),
            )
            base_style = overlay_dataclass(base_style, char_style) or base_style

        direct_style = extract_run_style(run_properties)
        resolved = overlay_dataclass(base_style, direct_style)

        return resolved or base_style
    

    def resolve_paragraph_style_by_id(
            self,
            style_id: str | None,
            visited: frozenset[str] = frozenset(),
        ) -> ParagraphStyle:

        if style_id is None:
            return self.default_paragraph_style
        
        cached = self._resolved_paragraph_styles.get(style_id)
        if cached is not None:
            return cached

        if style_id in visited:
            raise StyleResolutionError(
                f"Circular style dependency detected: {style_id}"
            )
        
        style = self.styles.get(style_id)

        if style is None:
            return self.default_paragraph_style
        
        if style.style_type != "paragraph":
            raise StyleResolutionError(
                f"Invalid style type: {style_id}."
            )

        parent_style = self.resolve_paragraph_style_by_id(
            style.based_on,
            visited | {style_id},
        )

        resolved = overlay_dataclass(
            parent_style,
            style.paragraph_style,
        )

        if resolved is None:
            return self.default_paragraph_style
        
        self._resolved_paragraph_styles[style_id] = resolved

        return resolved
    

    def resolve_paragraph_style(self, paragraph: _Element) -> ParagraphStyle:
        paragraph_properties = paragraph.find("w:pPr", NS)
        if paragraph_properties is None:
            return self.default_paragraph_style
        
        style_node = paragraph_properties.find("w:pStyle", NS)
        style_id = None

        if style_node is not None:
            style_id = get_attr(style_node, "val")
        
        base_style = self.resolve_paragraph_style_by_id(style_id)

        direct_style = extract_paragraph_style(paragraph_properties)

        resolved = overlay_dataclass(
            base_style,
            direct_style,
        )

        return resolved or self.default_paragraph_style


    def resolve_paragraph_run_style(
            self,
            paragraph: _Element,
    ) -> RunStyle:

        pstyle_node = paragraph.find("w:pPr/w:pStyle", NS)
        style_id = get_attr(pstyle_node, "val") if pstyle_node is not None \
            else self._default_paragraph_style_id
        return self._paragraph_run_base(style_id)


    def _paragraph_run_base(
            self,
            style_id: str | None,
            visited: frozenset[str] = frozenset(),
    ) -> RunStyle:

        if style_id is None or style_id in visited:
            return self.default_run_style
        
        style = self.styles.get(style_id)
        if style is None or style.style_type != "paragraph":
            return self.default_run_style
        
        parent = self._paragraph_run_base(style.based_on, visited | {style_id})

        return overlay_dataclass(parent, style.run_style) or parent


    def resolve_table_style_by_id(
            self,
            style_id: str | None,
            visited: frozenset[str] = frozenset(),
        ) -> TableStyle:

        if style_id is None:
           return self.default_table_style
        
        cached = self._resolved_table_styles.get(style_id)
        if cached is not None:
            return cached

        if style_id in visited:
            raise StyleResolutionError(
                f"Circular style dependency detected: {style_id}"
            )
        
        style = self.styles.get(style_id)

        if style is None:
            return self.default_table_style
        
        if style.style_type != "table":
            raise StyleResolutionError(
                f"Invalid style type: {style_id}."
            )

        parent_style = self.resolve_table_style_by_id(
            style.based_on,
            visited | {style_id},
        )

        resolved = overlay_dataclass(
            parent_style,
            style.table_style,
        )

        if resolved is None:
            return self.default_table_style
        
        self._resolved_table_styles[style_id] = resolved

        return resolved
    
    
    def resolve_table_style(self, table: _Element) -> TableStyle:
        table_properties = table.find("w:tblPr", NS)
        if table_properties is None:
            return self.default_table_style
        
        style_node = table_properties.find("w:tblStyle", NS)
        style_id = None
        
        if style_node is not None:
            style_id = get_attr(style_node, "val")

        base_style = self.resolve_table_style_by_id(style_id)

        direct_style = extract_table_style(table_properties)

        resolved = overlay_dataclass(
            base_style,
            direct_style,
        )

        return resolved or self.default_table_style
    

    def resolve_row_style(self, table_row: _Element, table_style: TableStyle) -> TableRowStyle:
        row_properties = table_row.find("w:trPr", NS)

        direct_style = extract_table_row_style(row_properties)

        resolved = overlay_dataclass(
            self.default_table_row_style,
            direct_style,
        )

        return resolved or self.default_table_row_style
    
    
    def resolve_cell_style(self, table_cell: _Element, table_style: TableStyle, row_style: TableRowStyle) -> TableCellStyle:
        cell_properties = table_cell.find("w:tcPr", NS)

        direct_style = extract_table_cell_style(cell_properties)

        inherited_margins = direct_style.margins
        if inherited_margins is None:
            inherited_margins = table_style.margins

        resolved = TableCellStyle(
            shading=direct_style.shading,
            shading_fill=direct_style.shading_fill,
            margins=inherited_margins,
            grid_span=direct_style.grid_span,
            v_alignment=direct_style.v_alignment,
        )

        return resolved