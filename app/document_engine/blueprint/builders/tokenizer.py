from enum import Enum, auto
from dataclasses import dataclass

from app.document_engine.blueprint.errors import PlaceholderSyntaxError


DOUBLE_QUOTES = frozenset('"“”„«»')
SINGLE_QUOTES = frozenset("'‘’‚")


class TK(Enum):
    IDENT = auto()
    STRING = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    EQ = auto()


@dataclass
class Token:
    kind: TK
    value: str


def _quote_class(ch: str) -> frozenset[str] | None:
    if ch in DOUBLE_QUOTES:
        return DOUBLE_QUOTES
    if ch in SINGLE_QUOTES:
        return SINGLE_QUOTES
    return None


def tokenize_placeholder(
    content: str,
) -> list[Token]:
    
    tokens = []
    i = 0
    n = len(content)

    while i < n:
        ch = content[i]

        if ch.isspace():
            i += 1

        elif ch == '(':
            tokens.append(Token(TK.LPAREN, ch))
            i += 1
        elif ch == ')':
            tokens.append(Token(TK.RPAREN, ch))
            i += 1
        elif ch == ',':
            tokens.append(Token(TK.COMMA, ch))
            i += 1
        elif ch == '=':
            tokens.append(Token(TK.EQ, ch))
            i += 1

        elif (quotes := _quote_class(ch)) is not None:
            i, buf = i + 1, []
            while i < n:
                c = content[i]
                if c == '\\' and i + 1 < n:
                    buf.append(content[i+1])
                    i += 2
                elif c in quotes:
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            else:
                raise PlaceholderSyntaxError(
                    f"Missing closing quote in placeholder: {content}."
                )

            tokens.append(Token(TK.STRING, "".join(buf)))

        elif ch.isalnum() or ch == '_':
            j = i+1
            while j < n and (content[j].isalnum() or content[j] in ('_', '.')):
                j += 1
            tokens.append(Token(TK.IDENT, content[i:j]))
            i = j

        else:
            raise PlaceholderSyntaxError(
                f"Unexpected character '{ch}' in placeholder: {content}."
            )
        
    return tokens