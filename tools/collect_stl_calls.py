import subprocess
import tempfile
import json
from pathlib import Path

from multiprocessing.pool import ThreadPool

from tqdm import tqdm


def process_file(path: Path, ch: Path, print_errors=False):
    with tempfile.TemporaryDirectory(delete=False) as build_dir:
        build_dir = Path(build_dir)

        with open(build_dir / 'compile_commands.json', 'w') as db_file:
            db_file.write(
                json.dumps([{
                    'directory': str(build_dir),
                    'command': f'/usr/bin/c++ -DNDEBUG -std=c++23 {path}',
                    'file': str(path),
                }]))

        stderr = None if print_errors else subprocess.DEVNULL

        result = subprocess.run(
            [ch, '-p', build_dir, '--json-out', '--punctuation=skip', path],
            stdout=subprocess.PIPE,
            stderr=stderr,
            check=True)

    with open(path, 'rb') as f:
        code = f.read()

    tokens = json.loads(result.stdout)["tokens"]

    ret = []
    num_page_comments = 0

    for idx, token in enumerate(tokens):
        type = token['type']
        if type == 'comment':
            text = code[token['offset']:token['offset'] +
                        token['length']].decode()
            if text.startswith('// PAGE: '):
                current_page = text[9:].strip()
                num_page_comments += 1
            if text == '/* -> */':
                dest = tokens[idx + 1]
                if 'link' not in dest:
                    continue

                ret.append({
                    'page': current_page,
                    'overload': dest['link'],
                })

    return ret, (num_page_comments - len(ret))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Input file or directory', type=Path)

    args = parser.parse_args()

    base = Path(__file__).parent
    ch = base.parent / 'build' / 'clang-highlight'

    if args.input.is_file():
        ret, failures = process_file(args.input, ch, print_errors=True)
        print(json.dumps(ret, indent=2))
    else:
        # Build list of files
        files = list(sorted(args.input.glob("**/*.cpp")))

        pool = ThreadPool()
        result = list(tqdm(pool.imap(lambda x: process_file(x, ch), files), total=len(files)))

        result = list(zip(files, result))
        result = sorted(result, key=lambda x: x[1][1])

        for f, res in result:
            if res[1] != 0:
                print(f, res[1])

        print(f"Failures in total: {sum([res[1][1] for res in result])}")
