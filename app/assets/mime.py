import mimetypes

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOTX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.template"

mimetypes.add_type(DOCX_MIME, ".docx")
mimetypes.add_type(DOTX_MIME, ".dotx")

def detect_mime_type(filename: str) -> str:
    mime_type, _ = mimetypes.guess_type(filename)

    return mime_type or "application/octet-stream"