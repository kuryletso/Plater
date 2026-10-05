import io
import zipfile
from lxml import etree

from app.document_engine.rendering.docx.content_types_xml import build_content_types
from app.document_engine.rendering.docx.rels import RelationshipRegistry
from app.document_engine.rendering.docx.constants import (
    IMAGE_CONTENT_TYPES,
    ROOT_RELS,
    FONT_CONTENT_TYPES,
)

from app.document_engine.rendering.errors import PackageError


def _rels_path(owner: str) -> str:
    # "word/document.xml" -> "word/_rels/document.xml.rels"
    directory, _, name = owner.rpartition("/")
    prefix = f"{directory}/" if directory else ""
    return f"{prefix}_rels/{name}.rels"


class DocxPackage:
    def __init__(self) -> None:
        self._parts: dict[str, bytes] = {}
        self._overrides: dict[str, str] = {}
        self._extensions: dict[str, str] = {}
        self._rels: dict[str, RelationshipRegistry] = {}

    def add_xml(
        self,
        path: str,
        element: etree._Element,
        content_type: str,
    ) -> None:
        
        self._parts[path] = etree.tostring(
            element,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
        self._overrides["/" + path] = content_type

    def add_image(
        self,
        path: str,
        data: bytes,
    ) -> None:
        
        self._parts[path] = data
        ext = path.rsplit(".", 1)[-1].lower()
        if ext not in IMAGE_CONTENT_TYPES:
            raise PackageError(
                f"Unsupported image extension [{ext}] in file {path}."
            )
        
        self._extensions[ext] = IMAGE_CONTENT_TYPES[ext]


    def add_font(
            self,
            path: str,
            data: bytes,
    ) -> None:

        self._parts[path] = data
        ext = path.rsplit(".", 1)[-1].lower()
        if ext not in FONT_CONTENT_TYPES:
            raise PackageError(
                f"Unsupported font extension [{ext}] in file {path}."
            )

        self._extensions[ext] = FONT_CONTENT_TYPES[ext]


    def add_rels(
        self,
        path: str,
        element: etree._Element,
    ) -> None:
        
        self._parts[path] = etree.tostring(
            element,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )


    def add_relationship(
        self,
        owner: str,
        rtype: str,
        target: str,
    ) -> str:
        
        return self._rels.setdefault(owner, RelationshipRegistry()).add(rtype, target)


    def add_document_relationship(
        self,
        rtype: str,
        target: str,
    ) -> str:
        
        return self.add_relationship("word/document.xml", rtype, target)


    def to_bytes(self) -> bytes:

        content_types = build_content_types(self._overrides, self._extensions)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                etree.tostring(
                    content_types,
                    xml_declaration=True,
                    encoding="UTF-8",
                    standalone=True,
                )
            )
            zf.writestr("_rels/.rels", ROOT_RELS)

            for owner, registry in self._rels.items():
                rels_el = registry.build()
                if rels_el is not None:
                    zf.writestr(
                        _rels_path(owner),
                        etree.tostring(
                            rels_el,
                            xml_declaration=True,
                            encoding="UTF-8",
                            standalone=True,
                        )
                    )

            for path, data in self._parts.items():
                zf.writestr(path, data)

        return buf.getvalue()