
import clang.cindex as cl

from pathlib import Path
import dataclasses
from dataclasses import dataclass
import html
import subprocess
import urllib
import json

from sortedcontainers import SortedDict

from lsp_client import LSPClient

@dataclass
class Link:
    file: Path
    line: int
    character: int
    qualified_name: str

@dataclass
class Token:
    token: cl.Token = None
    cursor: cl.Cursor = None
    css_class: str = None
    link: Link = None

TOKEN_CSS_MAP = {
    cl.TokenKind.COMMENT: 'c',
    cl.TokenKind.KEYWORD: 'k',
    cl.TokenKind.PUNCTUATION: 'p',
}

def qualified_name(cursor):
    parent = cursor.semantic_parent

    if parent is None or parent.kind == cl.CursorKind.TRANSLATION_UNIT:
        return cursor.displayname

    return qualified_name(parent) + '::' + cursor.displayname

class Processor:
    def __init__(self, build_dir: Path, file_path: Path):
        build_dir = Path(build_dir)

        with open(file_path, 'rb') as f:
            self.text = f.read()

        self.token_map = SortedDict()

        self.lsp_client = LSPClient(build_dir)
        self.lsp_client.initialize(build_dir.parent)

    def process(self, cursor: cl.Cursor):
        self.root = cursor
        self.file = cursor.extent.start.file.name

        # Initialize tokens
        for token in cursor.get_tokens():
            self.token_map[token.extent.start.offset] = Token(token=token, cursor=cursor)

        # Visit AST
        self.visit(cursor)

        # Decide on CSS classes
        self.generate_classes()

        # self.query_lsp()


    def process_tokens(self, unit: cl.TranslationUnit):
        self.root = unit.cursor
        self.file = self.root.extent.start.file.name

        # for token in unit.get_tokens(extent=unit.get_extent(input_file, (0, len(text)))):
        for token in unit.cursor.get_tokens():
            if (not token.location.file) or token.location.file.name != unit.cursor.extent.start.file.name:
                continue

            self.token_map[token.extent.start.offset] = Token(token=token, cursor=token.cursor)


    def token(self, cursor, token):
        start = token.extent.start.offset

        if start in self.token_map:
            # Don't overwrite macro instantiations
            if self.token_map[start].cursor.kind == cl.CursorKind.MACRO_INSTANTIATION:
                return

        self.token_map[start] = Token(token=token, cursor=cursor)

    def visit(self, cursor: cl.Cursor):
        # Ignore anything not in our file
        if not cursor.extent.start.file or cursor.extent.start.file.name != self.file:
            return

        tokens = list(cursor.get_tokens())
        tokenIdx = 0

        if cursor.kind == cl.CursorKind.MACRO_INSTANTIATION:
            # macro instantiations cover the entire call, including arguments.
            # we just want to mark the macro name
            tokens = [tokens[0]]

        offset = cursor.extent.start.offset

        for child in cursor.get_children():
            child_start = child.extent.start.offset

            while offset < child_start and tokenIdx < len(tokens):
                tok_start = tokens[tokenIdx].extent.start.offset

                if tok_start < offset:
                    tokenIdx += 1
                    continue

                self.token(cursor, tokens[tokenIdx])
                offset = tokens[tokenIdx].extent.end.offset
                tokenIdx += 1

            self.visit(child)

            offset = child.extent.end.offset

        for token in tokens[tokenIdx:]:
            tok_start = token.extent.start.offset

            if tok_start < offset:
                continue

            self.token(cursor, token)
            offset = token.extent.end.offset

    def generate_classes(self):
        for start, token in self.token_map.items():
            definition: cl.Cursor = token.cursor.get_definition() or token.cursor

            cls = TOKEN_CSS_MAP.get(token.token.kind, None)

            if token.token.kind == cl.TokenKind.IDENTIFIER:
                if token.cursor.kind == cl.CursorKind.STRUCT_DECL or definition.kind == cl.CursorKind.STRUCT_DECL \
                    or token.cursor.kind == cl.CursorKind.CLASS_TEMPLATE or definition.kind == cl.CursorKind.CLASS_TEMPLATE:
                    cls = 'nc'
                elif token.cursor.kind == cl.CursorKind.VAR_DECL or definition.kind == cl.CursorKind.VAR_DECL \
                    or token.cursor.kind == cl.CursorKind.PARM_DECL or definition.kind == cl.CursorKind.PARM_DECL:
                    cls = 'nv'
                else:
                    cls = 'n'

            if token.token.kind == cl.TokenKind.LITERAL:
                if token.token.spelling.startswith('"') or token.token.spelling.startswith("'"):
                    cls = 's'
                else:
                    cls = 'm'

            if token.cursor.kind == cl.CursorKind.INCLUSION_DIRECTIVE or token.cursor.kind == cl.CursorKind.MACRO_INSTANTIATION:
                cls = 'cp'

            link = None
            if token.token.kind != cl.TokenKind.PUNCTUATION:
                if definition and definition.location.file and definition.location.file.name != self.file:
                    link = Link(file=definition.location.file.name, line=definition.location.line, character=definition.location.column, qualified_name=qualified_name(definition))

            token.css_class = cls
            # token.link = link

    def query_lsp(self):
        for offset, token in self.token_map.items():
            if token.link is not None:
                continue

            if token.token.kind != cl.TokenKind.IDENTIFIER:
                continue

            if token.cursor.kind == cl.CursorKind.INCLUSION_DIRECTIVE:
                continue

            print(f"Querying: {token.token.spelling} ({token.token.extent.start} in {self.file})")
            extent = token.token.extent

            # Caution: LSP line & column are zero-based
            decls = self.lsp_client.get_declaration(extent.start.file.name, extent.start.line - 1, extent.start.column - 1)

            if len(decls) == 0:
                continue

            # Exclude same-file refs for now
            path = urllib.parse.unquote(urllib.parse.urlparse(decls[0]['uri']).path)

            if path == self.file:
                continue

            print(decls)

            location = cl.SourceLocation.from_position(
                tu=token.cursor.translation_unit,
                file=cl.File.from_name(token.cursor.translation_unit, path),
                line=decls[0]['range']['start']['line'] + 1,
                column=decls[0]['range']['start']['character'] + 1,
            )

            dest = cl.Cursor.from_location(token.cursor.translation_unit, location)

            token.link = Link(
                file=Path(path),
                line=location.line,
                character=location.column,
                qualified_name=qualified_name(dest)
            )

    def add_clang_ast(self, clang_args):
        result = subprocess.run(['clang++', '-fsyntax-only', '-Xclang', '-ast-dump=json', *clang_args], capture_output=True, encoding='utf-8')

        if result.returncode != 0:
            print("clang++ did not exit cleanly", file=sys.stderr)

        ast = json.loads(result.stdout)

        @dataclass
        class State:
            file: str = None
            line: int = -1
            is_main_file: bool = False

        state = State()

        id_map = {}

        def handleLoc(loc, state):
            if 'file' in loc:
                state.file = loc['file']

                # print(f"Entering file {state.file} (vs. {self.file}")
                state.is_main_file = (Path(state.file).absolute() == Path(self.file))

            if 'line' in loc:
                state.line = loc['line']

        def visit(node, state):
            if node.get('kind', '') == 'MemberExpr':
                begin = node['range']['begin']['offset']
                end = node['range']['end']['offset']

                member = int(node['referencedMemberDecl'], base=0)
                print(f"{node['kind']} at {state.file}:{node['range']['begin']['offset']} refs to 0x{member:x}")
                ref_tuple = id_map.get(member, None)
                if not ref_tuple:
                    return

                ref, ref_state = ref_tuple

                print(f" => {ref['name']}")

                if end not in self.token_map:
                    return

                self.token_map[end].link = Link(file=Path(ref_state.file).absolute(),
                                            line=ref_state.line,
                                            character=ref['range']['begin']['col'],
                                            qualified_name=ref['name'])
                # idx_end = self.token_map.bisect_right(end)
                # for idx in range(idx_end-1, 0, -1):
                #     token_off, token = self.token_map.items()[idx]
                #     if token_off < begin:
                #         break
                #
                #     if token.token.kind == cl.TokenKind.PUNCTUATION:
                #         continue
                #
                #     if token.link is None:
                #         token.link =
                #
                #     break


        def traverse(node, state):
            if 'loc' in node:
                handleLoc(node['loc'], state)
            if 'range' in node:
                handleLoc(node['range']['begin'], state)

            if state.is_main_file:
                visit(node, state)

            if 'id' in node and 'mangledName' in node:
                id_map[int(node['id'], base=0)] = (node, dataclasses.replace(state))

            for child in node.get('inner', []):
                traverse(child, state)

        print("Got AST")
        traverse(ast, state)

    def dump(self):
        offset = 0

        for start, token in self.token_map.items():
            if start > offset:
                sys.stdout.write(self.text[offset:start].decode('utf8'))

            if token.cursor:
                sys.stdout.write(f"{token.cursor.kind.name}+{token.token.kind.name}({token.token.spelling})")
            else:
                sys.stdout.write(f"{token.token.kind.name}({token.token.spelling})")

            offset = token.token.extent.end.offset
        sys.stdout.flush()

    def dump_html(self, out):
        out.write("""<!doctype html>
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
                    <pre class="m-code">\n""")

        offset = 0

        for start, token in self.token_map.items():
            if start > offset:
                out.write(html.escape(self.text[offset:start].decode('utf8')))

            if token.link is not None:
                out.write(f'<a href="{token.link.file}#{token.link.qualified_name}">')
            if token.css_class is not None:
                out.write(f'<span class="{token.css_class}">')

            out.write(html.escape(token.token.spelling))

            if token.css_class is not None:
                out.write(f'</span>')
            if token.link is not None:
                out.write(f'</a>')

            offset = token.token.extent.end.offset
        out.write("</pre></body></html>\n")
        out.flush()

def get_system_includes():
    ret = subprocess.run(['clang++', '-E', '-Wp,-v', '-'], capture_output=True, stdin=subprocess.DEVNULL, check=True)

    includes = []

    for line in ret.stderr.decode('utf8').split('\n'):
        if line.startswith(' '):
            includes.append('-isystem')
            includes.append(line[1:])
            break

    return includes

if __name__ == "__main__":
    import sys

    db = cl.CompilationDatabase.fromDirectory(sys.argv[1])

    input_file = Path(sys.argv[2]).absolute()

    command = list(next(iter(db.getCompileCommands(input_file))).arguments)

    # Remove -- from command list, otherwise libclang's options do not work
    if '--' in command:
        command.remove('--')

    command = command[0:2] + get_system_includes() + command[2:]

    # print(command)

    index = cl.Index.create()

    unit = index.parse(path=None, args=command, options=cl.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

    diagnostics = [ diag for diag in unit.diagnostics if diag.severity > cl.Diagnostic.Warning ]
    if diagnostics:
        print("Parsing errors:")
        for diag in diagnostics:
            print(diag.format())

        sys.exit(1)

    #unit = cl.TranslationUnit.from_source(filename=None, args=list(command.arguments), options=cl.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

    # for cursor in unit.cursor.walk_preorder():
    #     if cursor.kind == cl.CursorKind.MACRO_INSTANTIATION:
    #         print("PREPROCESSING")

    # Token-based

    # current_offset = 0
    # for token in unit.get_tokens(extent=unit.get_extent(input_file, (0, len(text)))):
    #     if (not token.location.file) or token.location.file.name != unit.cursor.extent.start.file.name:
    #         continue
    #
    #     print(token.cursor.kind)
    #     start = token.extent.start.offset
    #     end = token.extent.end.offset
    #     if start > current_offset:
    #         sys.stdout.write(text[current_offset:start].decode('utf8'))
    #
    #     sys.stdout.write(token.spelling)
    #     current_offset = end

    # # Cursor based
    # for cursor in unit.cursor.walk_preorder():
    #     print(cursor.kind, cursor.extent)


    # for cursor in unit.cursor.walk_preorder():
    #     # if (not cursor.extent.start.file) or (cursor.extent.start.file.name != unit.cursor.extent.start.file.name):
    #         # continue
    #
    #     match = False
    #     cnt = 0
    #     for token in cursor.get_tokens():
    #         if token.spelling == 'annotations':
    #             match = True
    #             break
    #         else:
    #             cnt += 1
    #             if cnt > 20:
    #                 break
    #
    #     if not match:
    #         continue
    #
    #     if cursor.extent.start.line != 78:
    #         continue
    #
    #     print(f"Annotations token: {cursor.extent.start} {cursor.displayname} {cursor.kind} {cursor.referenced}")

    # for cursor in unit.cursor.walk_preorder():
    #     if cursor.kind != cl.CursorKind.DECL_REF_EXPR:
    #         continue
    #
    #     if cursor.extent.start.line != 10:
    #         continue
    #
    #     print(f"{cursor.kind=} {cursor.type.spelling=} {cursor.referenced.displayname=}")
    #
    # def recurse(cursor):
    #     return {
    #         'kind': cursor.kind.name,
    #         'children': [
    #             recurse(c) for c in cursor.get_children()
    #         ]
    #     }
    #
    # data = recurse(unit.cursor)
    # print(json.dumps(data, indent=2))

    proc = Processor(sys.argv[1], input_file)
    proc.process(unit.cursor)
    proc.add_clang_ast(command[2:])
    # proc.process_tokens(unit)
    # proc.dump()

    with open('out.html', 'w') as f:
        proc.dump_html(f)
