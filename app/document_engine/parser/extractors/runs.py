from lxml.etree import _Element
from pathlib import PurePosixPath

from app.document_engine.parser.context import ParserContext
from app.document_engine.parser.models.inlines import RunNode, ImageNode, RunStyle
from app.document_engine.parser.namespaces import NS
from app.document_engine.parser.errors import ParserSecurityError, ParserAssetError, ParserFormatError, UnsupportedFeatureError

from app.core.errors import Layer
from app.document_engine.utils.intrinsic_emu import intrinsic_emu

type ParsedInlineNode = RunNode | ImageNode

MAX_IMAGE_SIZE_BYTES = 25 * 1024 * 1024


def extract_run_text(run: _Element) -> str:
    parts: list[str] = []

    for child in run:
        tag = child.tag

        if tag == f"{{{NS["w"]}}}t":
            if child.text:
                parts.append(child.text)

        elif tag == f"{{{NS["w"]}}}tab":
            parts.append("\t")

        elif tag == f"{{{NS["w"]}}}cr":
            parts.append("\n")

        elif tag == f"{{{NS["w"]}}}br":
            br_type = child.get(f"{{{NS["w"]}}}type")
            if br_type in (None, "textWrapping"):
                parts.append("\n")

    return "".join(parts)


def extract_extent(
    run: _Element,
    context: ParserContext,
    target: str,
) -> tuple[int, int]:
    
    extent = run.find(".//wp:extent", NS)

    if extent is not None:
        cx = extent.get("cx")
        cy = extent.get("cy")
        if cx is not None and cy is not None:
            try:
                return int(float(cx)), int(float(cy))       # Some editors (Google Docs, LibreOffice) emit twips as float "10081.0"
            except (ValueError, OverflowError):
                pass

    context.diagnostics.warn(
        Layer.PARSER,
        "image_missing_extent",
        "Image has no usable wp:extent; size set to 0.",
        target=target,
    )
    return 0,0


def parse_image(run: _Element, context: ParserContext) -> ImageNode | None:
    blip = run.find(".//a:blip", NS)
    if blip is None:
        return None
    
    relationship_id = blip.get(f"{{{NS["r"]}}}embed")
    if relationship_id is None:
        return None
    
    relationship = context.relationships.get(relationship_id)
    if relationship is None:
        return None
    if relationship.is_external:
        raise UnsupportedFeatureError(
            "External image references are not supported."
        )
    
    target = relationship.target
    
    normalized_path = PurePosixPath(target)

    uncompressed_size = context.archive.get_uncompressed_size(normalized_path.as_posix())
    if uncompressed_size > MAX_IMAGE_SIZE_BYTES:
        raise ParserSecurityError(
            f"Image exceeds size limit:"
            f"{uncompressed_size} bytes."
        )
    
    try:
        image_bytes = context.archive.read_bytes(normalized_path.as_posix())
    except ParserFormatError as e:
        raise ParserAssetError(
            f"Invalid image reference {target}."
        ) from e

    width_emu, height_emu = extract_extent(run, context, target)

    if width_emu == 0 or height_emu == 0:
        fallback = intrinsic_emu(image_bytes)
        if fallback is None:
            context.diagnostics.warn(
                Layer.PARSER,
                "image_unsizable",
                "Image has no extent and unreadable dimensions; skipped.",
                target=target,
            )
            return None
        width_emu, height_emu = fallback

    asset_id = context.assets.add(
        filename=PurePosixPath(target).name,
        data=image_bytes,
    )
    
    return ImageNode(
        asset_id=asset_id,
        width_emu=width_emu,
        height_emu=height_emu,
    )


def parse_inline(
        run: _Element,
        context: ParserContext,
        paragraph_base: RunStyle,
) -> list[ParsedInlineNode]:

    result = []

    image = parse_image(run, context)
    if image is not None:
        result.append(image)

    text = extract_run_text(run)
    if text:
        result.append(
            RunNode(
                text=text,
                style=context.style_resolver.resolve_run_style(run, paragraph_base),
            )
        )

    return result