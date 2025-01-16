import subprocess
import tempfile
import json
import dacite
from typing import List, Optional
from pathlib import Path
from contextlib import contextmanager
import importlib.resources

from .data import Token, HighlightedCode, TokenType, Link
from . import map_stl

__all__ = ['Token', 'TokenType', 'Link', 'HighlightedCode', 'run']

# Find our C++ part
_ch = None
with importlib.resources.path('clang_highlight._util', 'clang-highlight') as p:
    _ch = p
    assert _ch.exists(), "Could not find clang-highlight utility"


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
        with tempfile.NamedTemporaryFile(mode='w',
                                         suffix='.cpp',
                                         delete_on_close=False) as f:
            f.write(code)
            f.close()
            yield Path(f.name)
    else:
        raise RuntimeError("need either filename or code")


def run(filename: Path = None,
        code: str = None,
        args=['-DNDEBUG', '-std=c++23'],
        build_dir=None,
        punctuation='keep',
        cppref=False) -> HighlightedCode:

    with code_file_context(filename, code) as code_filename, \
         build_dir_context(filename, build_dir, args) as ch_build_dir:

        cmd = [
            _ch, '-p', ch_build_dir, f'--punctuation={punctuation}',
            '--json-out', code_filename
        ]
        result = subprocess.run(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                check=True)

        with open(code_filename, 'rb') as f:
            code = f.read()

    data = json.loads(result.stdout)

    def parse_token(d):
        return dacite.from_dict(data_class=Token,
                                data=d,
                                config=dacite.Config(cast=[TokenType, Path]))

    tokens = [parse_token(d) for d in data['tokens']]

    highlighted = HighlightedCode(filename=filename,
                                  code=code,
                                  tokens=tokens,
                                  diagnostics=result.stderr)

    if cppref:
        map_stl.resolve_stl(highlighted)

    return highlighted
