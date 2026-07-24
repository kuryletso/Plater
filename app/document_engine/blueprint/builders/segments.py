from app.core.errors import Layer

from app.document_engine.blueprint.template_builder import TemplateBuilderContext
from app.document_engine.blueprint.models.segment import (
    ImageSegment,
    TextSegment,
    PlaceholderSegment,
    JoinedPlaceholderSegment,
    GroupedPlaceholderSegment,
    TextStyleBlueprint,
)
from app.document_engine.blueprint.builders.tokenizer import tokenize_placeholder, TK, Token
from app.document_engine.blueprint.errors import PlaceholderSyntaxError

from app.document_engine.normalization.models.inlines import NormalizedImageNode, NormalizedTextNode, NormalizedTextStyle


def text_style_bp_from_normalized(
    style: NormalizedTextStyle,
) -> TextStyleBlueprint:
    
    return TextStyleBlueprint(
        bold=style.bold,
        italic=style.italic,
        underline=style.underline,
        font_name=style.font_name,
        font_size=style.font_size,
        color=style.color,
    )


def image_segment_bp_from_normalized(
    image: NormalizedImageNode,
) -> ImageSegment:
    
    return ImageSegment(
        type="image",
        asset_id=image.asset_id,
        width_emu=image.width_emu,
        height_emu=image.height_emu,
    )


def split_placeholder_key(
    key: str,
) -> tuple[str, str | None]:
    
    parts = key.split(".")

    if len(parts) == 1:
        return key.lower(), None
    
    if len(parts) != 2:
        raise PlaceholderSyntaxError(
            f"Invalid placeholder key '{key}': only one '.' separator is allowed."
        )
    
    base, language = parts

    if not base:
        raise PlaceholderSyntaxError(
            f"Invalid placeholder key '{key}': missing base before '.'."
        )
    
    if not language:
        raise PlaceholderSyntaxError(
            f"Invalid placeholder key '{key}': missing language parameter."
        )
    
    return base.lower(), language.upper()


def _parse_grouped(
    tokens: list[Token],
    style: TextStyleBlueprint,
    context: TemplateBuilderContext,
) -> GroupedPlaceholderSegment:
    
    groups = []
    separator = ", "

    i, n = 1, len(tokens)

    in_group = False
    curr_group = []

    while i < n:
        t = tokens[i]

        if t.kind == TK.LPAREN:
            if in_group:
                raise PlaceholderSyntaxError(
                    "Unexpected '(' in grouped placeholder."
                )
            else:
                in_group = True

        elif t.kind == TK.RPAREN:
            if in_group:
                groups.append(tuple(curr_group))
                curr_group.clear()
                in_group = False
            else:
                pass

        elif t.kind == TK.IDENT:
            if in_group:
                base, language = split_placeholder_key(t.value)
                language = language or context.default_language
                if language not in context.languages:
                    raise PlaceholderSyntaxError(
                        f"Invalid placeholder key '{t.value}': invalid language."
                    )
                ph_type = context.register_placeholder(base)
                
                curr_group.append(
                    PlaceholderSegment(
                        type="placeholder",
                        key=base,
                        language=language,
                        ph_type=ph_type,
                        style=style,
                    )
                )
            elif t.value == "sep":
                if i+2 < n \
                and tokens[i+1].kind == TK.EQ \
                and tokens[i+2].kind == TK.STRING:
                    separator = tokens[i+2].value
                    i += 2
                else:
                    raise PlaceholderSyntaxError(
                        "Invalid separator syntax in grouped placeholder."
                    )

            else:
                raise PlaceholderSyntaxError(
                    f"Ungrouped key {t.value} in grouped placeholder."
                )
            
        elif t.kind == TK.STRING:
            if in_group:
                curr_group.append(
                    TextSegment(
                        type="text",
                        text=t.value,
                        style=style,
                    )
                )
            else:
                raise PlaceholderSyntaxError(
                    f"Ungrouped text literal {t.value} in grouped placeholder."
                )
            
        elif t.kind == TK.COMMA:
            pass

        elif t.kind == TK.EQ:
            raise PlaceholderSyntaxError(
                "Unexpected '=' in grouped placeholder."
            )
        
        i += 1


    return GroupedPlaceholderSegment(
        type="placeholder_group",
        items=tuple(groups),
        separator=separator,
        style=style,
    )


def _parse_joined(
    tokens: list[Token],
    style: TextStyleBlueprint,
    context: TemplateBuilderContext,
) -> JoinedPlaceholderSegment:
    
    items = []
    separator = ", "

    i, n = 0, len(tokens)

    while i < n:
        t = tokens[i]

        if t.kind in (TK.LPAREN, TK.RPAREN, TK.EQ):
            raise PlaceholderSyntaxError(
                f"Unexpected '{t.value}' in joined placeholder."
            )
        
        elif t.kind == TK.IDENT:
            if t.value == "sep":
                if i+2 < n \
                and tokens[i+1].kind == TK.EQ \
                and tokens[i+2].kind == TK.STRING:
                    separator = tokens[i+2].value
                    i += 2
                else:
                    raise PlaceholderSyntaxError(
                        "Invalid separator syntax in joined placeholder."
                    )
            else:
                base, language = split_placeholder_key(t.value)
                language = language or context.default_language
                if language not in context.languages:
                    raise PlaceholderSyntaxError(
                        f"Invalid placeholder key '{t.value}': invalid language."
                    )
                ph_type = context.register_placeholder(base)
                items.append(
                    PlaceholderSegment(
                        type="placeholder",
                        key=base,
                        language=language,
                        ph_type=ph_type,
                        style=style,
                    )
                )

        elif t.kind == TK.STRING:
            items.append(
                TextSegment(
                    type="text",
                    text=t.value,
                    style=style,
                )
            )

        elif t.kind == TK.COMMA:
            pass

        i += 1

    return JoinedPlaceholderSegment(
        type="placeholder_join",
        items=tuple(items),
        separator=separator,
        style=style,
    )


def _parse_simple(
    tokens: list[Token],
    style: TextStyleBlueprint,
    context: TemplateBuilderContext,
) -> PlaceholderSegment:
    
    if len(tokens) > 1:
        raise PlaceholderSyntaxError(
            "Invalid placeholder syntax."
        )
    
    t = tokens[0]
    if t.kind == TK.IDENT:
        base, language = split_placeholder_key(t.value)
        language = language or context.default_language
        if language not in context.languages:
            raise PlaceholderSyntaxError(
                f"Invalid placeholder key '{t.value}': invalid language."
            )
        ph_type = context.register_placeholder(base)

        return PlaceholderSegment(
            type="placeholder",
            key=base,
            language=language,
            ph_type=ph_type,
            style=style,
        )

    else:
        raise PlaceholderSyntaxError(
            "Invalid placeholder syntax."
        )


def parse_placeholder(
    content: str,
    style: TextStyleBlueprint,
    context: TemplateBuilderContext,
) -> PlaceholderSegment | JoinedPlaceholderSegment | GroupedPlaceholderSegment:
    
    inner = content[2:-2].strip()
    tokens = tokenize_placeholder(inner)

    if not tokens:
        raise PlaceholderSyntaxError(
            f"Empty placeholder in: {content}."
        )
    
    if tokens[0].kind == TK.LPAREN:
        return _parse_grouped(tokens, style, context)
    elif any(t.kind == TK.COMMA for t in tokens):
        return _parse_joined(tokens, style, context)
    else:
        return _parse_simple(tokens, style, context)



def extract_segments(
    node: NormalizedTextNode,
    context: TemplateBuilderContext,
) -> list[
    TextSegment
    | PlaceholderSegment
    | JoinedPlaceholderSegment
    | GroupedPlaceholderSegment
] :
    
    style = text_style_bp_from_normalized(node.style)
    text = node.text
    segments = []

    placeholder_index = []
    i = 0
    n = len(text)

    in_placeholder = False
    start = None
    while i < n-1:

        if text[i] == '{' and text[i+1] == '{':
            in_placeholder = True
            start = i
            i += 2
            in_string = False
            string_char = ''

            while i < n:
                ch = text[i]

                if in_string:
                    if ch == '\\':
                        i += 2
                        continue
                    if ch == string_char:
                        in_string = False
                    
                elif ch in ('"', "'"):
                    in_string = True
                    string_char = ch

                elif ch == '}' and i+1 < n and text[i+1] == '}':
                    placeholder_index.append((start, i+2))
                    i += 2
                    in_placeholder = False
                    break

                i += 1
        else:
            i += 1

    if in_placeholder:
        context.diagnostics.warn(
            Layer.BLUEPRINT,
            "unclosed_placeholder",
            f"Unclosed placeholder at index [{start}]; treated as literal text.",
            content=text[start:],
        )

    if placeholder_index:
        last = 0

        for start, end in placeholder_index:

            if start > last:
                segments.append(
                    TextSegment(
                        type="text",
                        text=text[last:start],
                        style=style,
                    )
                )

            try:
                segments.append(
                    parse_placeholder(
                        content=text[start:end],
                        style=style,
                        context=context,
                    )
                )
            except PlaceholderSyntaxError as e:     # WARNING
                context.diagnostics.warn(
                    Layer.BLUEPRINT,
                    e.code,
                    str(e),
                    content=text[start:end]
                )
                segments.append(
                    TextSegment(
                        type="text",
                        text=text[start:end],
                        style=style,
                    )
                )

            last = end

        if last < n:
            segments.append(
                TextSegment(
                    type="text",
                    text=text[last:],
                    style=style,
                )
            )

    else:
        segments.append(
            TextSegment(
                type="text",
                text=text,
                style=style,
            )
        )

    return segments