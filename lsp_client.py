import subprocess
import json
import os

from pathlib import Path


class LSPClient:

    def __init__(self, build_dir: Path):
        self.process = subprocess.Popen(["clangd", f"--compile-commands-dir={build_dir}"],
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)
        self.req_id = 0
        self.open_files = set()

    def request(self, method, params, read_response=True):
        req = {
            'jsonrpc': "2.0",
            'method': method,
            'params': params,
        }
        if read_response:
            self.req_id += 1
            req['id'] = self.req_id

        body = json.dumps(req).encode('utf-8')

        self.process.stdin.write(
            f"Content-Length: {len(body)}\r\n\r\n".encode('utf-8'))
        self.process.stdin.write(body)
        self.process.stdin.flush()

        # sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n")
        # sys.stdout.write(body.decode('utf8'))
        # sys.stdout.flush()

        if read_response:
            while True:
                length = None
                while True:
                    header_line = self.process.stdout.readline(256).decode(
                        'ascii')
                    if header_line.lower().startswith("content-length: "):
                        length = int(header_line.partition(' ')[2].strip())
                    elif header_line == '\r\n':
                        break

                body = self.process.stdout.read(length).decode('utf8')
                body = json.loads(body)

                if 'id' in body and body['id'] == self.req_id:
                    return body

    def initialize(self, workspace):
        response = self.request(
            'initialize',
            dict(processId=os.getpid(),
                 clientInfo=dict(name='lsp_pygments', ),
                 capabilities=dict(
                     general=dict(positionEncodings=['utf-8'], ),
                     textDocument=dict(declaration=dict()),
                     workspace=dict(),
                     offsetEncoding=['utf-8'],
                 ),
                 workspaceFolders=[
                     dict(uri=f"file://{Path(workspace).absolute()}",
                          name="project")
                 ]))

        self.request('initialized', dict(), False)

    def get_declaration(self, file_path: Path, line: int, character: int):
        file_path = Path(file_path).absolute()

        if file_path not in self.open_files:
            with open(file_path) as f:
                text = f.read()

            self.request(
                'textDocument/didOpen',
                dict(textDocument=dict(
                    uri=f"file://{file_path}",
                    languageId='cpp',
                    version=1,
                    text=text,
                ), ), False)

            self.open_files.add(file_path)

        response = self.request(
            'textDocument/declaration',
            dict(textDocument=dict(uri=f"file://{file_path}"),
                 position=dict(line=line, character=character)))

        return response['result']
