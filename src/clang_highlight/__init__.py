import subprocess
import tempfile
import json
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path
from contextlib import contextmanager
import importlib.resources

# Find our C++ part
_ch = None
with importlib.resources.path('clang_highlight._util', 'clang-highlight') as p:
    _ch = p
    assert _ch.exists(), "Could not find clang-highlight utility"


@dataclass
class HighlightedCode:
    """
    Code with highlighting information
    """

    filename: Path
    code: bytes
    tokens: List[dict]

    def __iter__(self):
        """
        Iterate over the tokenized code. Yields each text fragment and its
        corresponding token. Whitespace and ignored punctuation will result in
        `Ǹone` token.

        Example:
        >>> code = "void test() { }"
        >>> for text, token in run(code=code):
        ...     print(f"{text:<10} -> {token['type'] if token else None}")
        ...
        void       -> keyword
                   -> None
        test       -> name
        (          -> punctuation
        )          -> punctuation
                   -> None
        {          -> punctuation
                   -> None
        }          -> punctuation
        """

        offset = 0
        for token in self.tokens:
            to = token['offset']
            tl = token['length']

            if to > offset:
                yield self.code[offset:token['offset']].decode('utf8'), None

            yield self.code[to:to + tl].decode('utf8'), token

            offset = to + tl


@contextmanager
def build_dir_context(filename: Optional[Path], build_dir: Optional[Path],
                      args: List[str]):
    if build_dir is None:
        with tempfile.TemporaryDirectory() as build_dir:
            build_dir = Path(build_dir)

            with open(build_dir / 'compile_commands.json', 'w') as db_file:
                db_file.write(
                    json.dumps([{
                        'directory': str(build_dir),
                        'command': f'/usr/bin/c++ {" ".join(args)} {filename}',
                        'file': str(filename),
                    }]))

            yield build_dir
    else:
        yield build_dir


@contextmanager
def code_file_context(filename: Path = None, code: str = None):
    if filename:
        yield Path(filename)
    elif code:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete_on_close=False) as f:
            f.write(code)
            f.close()
            yield Path(f.name)
    else:
        raise RuntimeError("need either filename or code")


def run(filename: Path = None,
        code: str = None,
        args=['-DNDEBUG', '-std=c++23'],
        build_dir=None,
        punctuation='keep') -> HighlightedCode:

    with code_file_context(filename, code) as code_filename, \
         build_dir_context(filename, build_dir, args) as ch_build_dir:

        cmd = [
            _ch, '-p', ch_build_dir, f'--punctuation={punctuation}',
            '--json-out', code_filename
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, check=True)

        with open(code_filename, 'rb') as f:
            code = f.read()

    data = json.loads(result.stdout)

    return HighlightedCode(filename=filename, code=code, tokens=data['tokens'])
