"""
The output formats clang-highlight supports.
"""

from .data import HighlightedCode, TokenType
from typing import TextIO
from html import escape as html_escape
import dataclasses
from json import dump as json_dump
from enum import Enum
from pathlib import Path

TOKEN_TYPE_TO_CSS_CLASS = {
    TokenType.KEYWORD: "k",
    TokenType.NAME: "n",
    TokenType.STRING_LITERAL: "s",
    TokenType.STRING_LITERAL_ESCAPE: "se",
    TokenType.STRING_LITERAL_INTERPOLATION: "si",
    TokenType.NUMBER_LITERAL: "m",
    TokenType.OTHER_LITERAL: "l",
    TokenType.OPERATOR: "o",
    TokenType.PUNCTUATION: "p",
    TokenType.COMMENT: "c",
    TokenType.PREPROCESSOR: "cp",
    TokenType.PREPROCESSOR_FILE: "cpf",
    TokenType.VARIABLE: "nv",
}


def html_embed(code: HighlightedCode, f: TextIO):
    f.write('<pre class="m-code">')

    for text, token in code:
        if token:
            css = TOKEN_TYPE_TO_CSS_CLASS[token.type]
            f.write(f'<span class="{css}">')

            if token.link:
                if token.link.cppref:
                    f.write(
                        f'<a href="https://en.cppreference.com/w/{token.link.cppref}">'
                    )
                else:
                    if token.link.line != 0:
                        f.write(f'<a href="{token.link.file}#L{token.link.line}">')
                    else:
                        f.write(f'<a href="{token.link.file}">')

        f.write(html_escape(text))

        if token:
            if token.link:
                f.write("</a>")
            f.write("</span>")

    f.write("</pre>")


def html(code: HighlightedCode, f: TextIO):
    f.write("""<!doctype html>
<html>
    <head>
        <meta charset="UTF-8" />
        <link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Source+Sans+Pro:400,400i,600,600i%7CSource+Code+Pro:400,400i,600&amp;subset=latin-ext" />
        <link rel="stylesheet" href="https://static.magnum.graphics/m-dark.compiled.css" />
        <link rel="stylesheet" href="https://static.magnum.graphics/m-dark.documentation.compiled.css" />
        <style>
            .m-code a {
                color: inherit;
                text-decoration: none;
            }
            .m-code a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <pre class="m-code">""")

    html_embed(code, f)

    f.write("</body></html>\n")


def json(code: HighlightedCode, f: TextIO):
    def asdict_factory(data):
        def convert_value(obj):
            if isinstance(obj, Enum):
                return obj.value
            elif isinstance(obj, Path):
                return str(obj)
            return obj

        return dict((k, convert_value(v)) for k, v in data)

    json_dump(
        [dataclasses.asdict(t, dict_factory=asdict_factory) for t in code.tokens],
        f,
        indent=2,
    )
    f.write("\n")


FORMATTERS = {
    "html": html,
    "html_embed": html_embed,
    "json": json,
}
