from lxml import etree

from app.document_engine.rendering.docx.constants import PR_NS, REL_NS

REL_HEADER = f"{REL_NS}/header"
REL_FOOTER = f"{REL_NS}/footer"
REL_IMAGE = f"{REL_NS}/image"
REL_SETTINGS = f"{REL_NS}/settings"
REL_NUMBERING = f"{REL_NS}/numbering"
REL_FONT_TABLE = f"{REL_NS}/fontTable"
REL_FONT = f"{REL_NS}/font"


class RelationshipRegistry:
    def __init__(self) -> None:
        self._items: list[tuple[str, str, str]] = []        # rId, type, target
        self._counter = 0


    def add(
        self,
        rtype: str,
        target: str,
    ) -> str:
        
        self._counter += 1
        rid = f"rId{self._counter}"
        self._items.append((rid, rtype, target))

        return rid

    def build(self) -> etree._Element | None:

        if not self._items:
            return None
        root = etree.Element(f"{{{PR_NS}}}Relationships", nsmap={None: PR_NS})
        
        for rid, rtype, target in self._items:
            rel = etree.SubElement(root, f"{{{PR_NS}}}Relationship")
            rel.set("Id", rid)
            rel.set("Type", rtype)
            rel.set("Target", target)
        
        return root