from dataclasses import dataclass
from typing import Optional, List
from enum import Enum
from pathlib import Path

@dataclass
class Link:
    file: Path
    line: int
    column: int
    name: str
    qualified_name: str
    parameter_types: Optional[List[str]]
    cppref: Optional[str]


class TokenType(Enum):
    WHITESPACE = 'whitespace'
    KEYWORD = 'keyword'
    NAME = 'name'
    STRING_LITERAL = 'string_literal'
    NUMBER_LITERAL = 'number_literal'
    OTHER_LITERAL = 'other_literal'
    OPERATOR = 'operator'
    PUNCTUATION = 'punctuation'
    COMMENT = 'comment'
    PREPROCESSOR = 'preprocessor'
    VARIABLE = 'variable'
    OTHER = 'other'


@dataclass
class Token:
    """
    A single token representing a code fragment with semantic meaning.
    """

    offset: int
    length: int

    type: TokenType

    link: Optional[Link]


@dataclass
class HighlightedCode:
    """
    Code with highlighting information
    """

    filename: Path
    code: bytes
    tokens: List[Token]

    def __iter__(self):
        """
        Iterate over the tokenized code. Yields each text fragment and its
        corresponding token. Whitespace and ignored punctuation will result in
        `Ǹone` token.

        Example:
        >>> code = "void test() { }"
        >>> for text, token in run(code=code):
        ...     print(f"{text:<10} -> {token.type.name if token else None}")
        ...
        void       -> KEYWORD
                   -> None
        test       -> NAME
        (          -> PUNCTUATION
        )          -> PUNCTUATION
                   -> None
        {          -> PUNCTUATION
                   -> None
        }          -> PUNCTUATION
        """

        offset = 0
        for token in self.tokens:
            if token.offset > offset:
                yield self.code[offset:token.offset].decode('utf8'), None

            end = token.offset + token.length
            yield self.code[token.offset:end].decode('utf8'), token

            offset = end
