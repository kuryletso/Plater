from lxml import etree
from app.document_engine.rendering.docx.xml import qn, WORD_NSMAP

def build_document(
    blocks: list[etree._Element],
    sect_pr: etree._Element | None = None,
    background: str | None = None,
) -> etree._Element:
    
    root = etree.Element(qn("w:document"), nsmap=WORD_NSMAP)

    # (!) CT_Document order:
    # background > body

    if background is not None:
        etree.SubElement(root, qn("w:background")).set(qn("w:color"), background)

    body = etree.SubElement(root, qn("w:body"))

    for block in blocks:
        body.append(block)

    if sect_pr is not None:
        body.append(sect_pr)

    return root