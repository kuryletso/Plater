CT_NS  = "http://schemas.openxmlformats.org/package/2006/content-types"
PR_NS  = "http://schemas.openxmlformats.org/package/2006/relationships"   # == NS["pr"]
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CT_DOCUMENT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
CT_HEADER   = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
CT_FOOTER   = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
CT_SETTINGS = "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"
CT_NUMBERING = "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"
CT_FONT_TABLE = "application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"

CT_RELS = "application/vnd.openxmlformats-package.relationships+xml"
CT_XML  = "application/xml"

IMAGE_CONTENT_TYPES = {
    "png":  "image/png",
    "jpeg": "image/jpeg",
    "jpg":  "image/jpeg",
    "gif":  "image/gif",
    "bmp":  "image/bmp",
}

ROOT_RELS: bytes = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1"'
    b' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
    b' Target="word/document.xml"/>'
    b'</Relationships>'
)

FONT_CONTENT_TYPES = {
    "ttf": "application/x-font-ttf",
    "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
}