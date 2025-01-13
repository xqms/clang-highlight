import subprocess
import tempfile
import json
from dataclasses import dataclass
from typing import List
from pathlib import Path
import importlib.resources

_ch = None
with importlib.resources.path('clang_highlight._util', 'clang-highlight') as p:
    _ch = p
    assert _ch.exists()


@dataclass
class HighlightedCode:
    filename: Path
    code: bytes
    tokens: List[dict]

    def __iter__(self):
        offset = 0
        for token in self.tokens:
            to = token['offset']
            tl = token['length']

            if to > offset:
                yield self.code[offset:token['offset']].decode('utf8'), None

            yield self.code[to:to + tl].decode('utf8'), token

            offset = to + tl


def run(filename: Path,
        args=['-DNDEBUG', '-std=c++23'],
        build_dir=None,
        punctuation='keep') -> HighlightedCode:
    ch_args = [f'--punctuation={punctuation}', '--json-out', filename]

    if build_dir is None:
        with tempfile.TemporaryDirectory(delete=False) as build_dir:
            build_dir = Path(build_dir)

            with open(build_dir / 'compile_commands.json', 'w') as db_file:
                db_file.write(
                    json.dumps([{
                        'directory': str(build_dir),
                        'command': f'/usr/bin/c++ {" ".join(args)} {filename}',
                        'file': str(filename),
                    }]))

            result = subprocess.run([_ch] + ['-p', build_dir] + ch_args,
                                    stdout=subprocess.PIPE,
                                    check=True)
    else:
        result = subprocess.run([_ch] + ['-p', build_dir] + ch_args,
                                stdout=subprocess.PIPE,
                                check=True)

    with open(filename, 'rb') as f:
        code = f.read()

    data = json.loads(result.stdout)

    return HighlightedCode(filename=filename, code=code, tokens=data['tokens'])
