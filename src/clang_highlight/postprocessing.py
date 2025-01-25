"""
Postprocessing
"""

from .data import Token, TokenType, HighlightedCode
import re

INCLUDE_REGEX = re.compile(rb'(?P<stmt>#\s*include)\s*(?P<file>[<"].*[">])')

ESCAPE_REGEX = re.compile(
    rb'\\([\'"?\\abfnrtv]|[0-7]{3}|o\{[0-7]+\}|x[0-9a-fA-F]+|x\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|u\{[0-9a-fA-F]+\}|U[0-9a-fA-F]{8}|N\{[^\}]+\})'
)

STRING_INTERPOLATION_REGEX = re.compile(rb"\{(?=[^{]).*?\}")


def generate_include_file_tokens(h: HighlightedCode):
    new_tokens = []
    for tok in h.tokens:
        if tok.type == TokenType.PREPROCESSOR:
            text = h.code[tok.offset : tok.offset + tok.length]
            m = INCLUDE_REGEX.match(text)

            if not m:
                raise RuntimeError(
                    f"Could not parse include statement '{text.decode()}'"
                )

            stmt_begin, stmt_end = m.span("stmt")
            file_begin, file_end = m.span("file")

            new_tokens.append(
                Token(
                    offset=tok.offset + stmt_begin,
                    length=stmt_end - stmt_begin,
                    type=TokenType.PREPROCESSOR,
                )
            )
            new_tokens.append(
                Token(
                    offset=tok.offset + file_begin,
                    length=file_end - file_begin,
                    type=TokenType.PREPROCESSOR_FILE,
                    link=tok.link,
                )
            )
        else:
            new_tokens.append(tok)

    h.tokens = new_tokens


def escape_codes(h: HighlightedCode):
    new_tokens = []

    for tok in h.tokens:
        if tok.type != TokenType.STRING_LITERAL:
            new_tokens.append(tok)
            continue

        text = h.code[tok.offset : tok.offset + tok.length]

        if b'"' not in text:
            new_tokens.append(tok)
            continue

        prefix, _, _ = text.partition(b'"')

        if b"R" in prefix:
            new_tokens.append(tok)
            continue

        def insert(begin: int, end: int, type: TokenType):
            new_tokens.append(
                Token(offset=tok.offset + begin, length=end - begin, type=type)
            )

        pos = 0
        for m in ESCAPE_REGEX.finditer(text):
            begin, end = m.span()
            if begin > pos:
                insert(pos, begin, TokenType.STRING_LITERAL)

            insert(begin, end, TokenType.STRING_LITERAL_ESCAPE)

            pos = end

        if pos < len(text):
            insert(pos, len(text), TokenType.STRING_LITERAL)

    h.tokens = new_tokens


def string_interpolation(h: HighlightedCode):
    new_tokens = []

    for tok in h.tokens:
        if tok.type != TokenType.STRING_LITERAL:
            new_tokens.append(tok)
            continue

        text = h.code[tok.offset : tok.offset + tok.length]

        if b'"' not in text:
            new_tokens.append(tok)
            continue

        def insert(begin: int, end: int, type: TokenType):
            new_tokens.append(
                Token(offset=tok.offset + begin, length=end - begin, type=type)
            )

        pos = 0
        for m in STRING_INTERPOLATION_REGEX.finditer(text):
            begin, end = m.span()
            if begin > pos:
                insert(pos, begin, TokenType.STRING_LITERAL)

            insert(begin, end, TokenType.STRING_LITERAL_INTERPOLATION)

            pos = end

        if pos < len(text):
            insert(pos, len(text), TokenType.STRING_LITERAL)

    h.tokens = new_tokens


ALL = [generate_include_file_tokens, escape_codes, string_interpolation]
