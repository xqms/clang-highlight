from pathlib import Path
import tempfile
import json
import subprocess
import sys
import html
import base64

TOKEN_TYPE_TO_CSS_CLASS = {
    'keyword': "k",
    'name': "n",
    'string_literal': "s",
    'number_literal': "m",
    'other_literal': "l",
    'operator': "o",
    'punctuation': "p",
    'comment': "c",
    'preprocessor': "cp",
    'variable': "nv",
}

def overload_match(o1, o2):
    if o1['qualified_name'] != o2['qualified_name']:
        return False

    if o1['parameter_types'] != o2['parameter_types']:
        return False

    return True

def produce_svg(tokens, code: bytes, svg):
    cache_path = Path.home() / '.cache' / 'clang_highlight'
    cache_path.mkdir(parents=True, exist_ok=True)

    source_code_pro_normal = cache_path / 'source_code_pro_400.woff2'
    if not source_code_pro_normal.exists():
        subprocess.run(['wget', '-O', source_code_pro_normal, 'https://fonts.gstatic.com/s/sourcecodepro/v23/HI_SiYsKILxRpg3hIP6sJ7fM7PqlPevW.woff2'], check=True)

    with open(source_code_pro_normal, 'rb') as f:
        woff_normal = base64.b64encode(f.read()).decode()

    source_code_pro_bold = cache_path / 'source_code_pro_600.woff2'
    if not source_code_pro_bold.exists():
        subprocess.run(['wget', '-O', source_code_pro_bold, 'https://fonts.gstatic.com/s/sourcecodepro/v23/HI_SiYsKILxRpg3hIP6sJ7fM7PqlPevW.woff2'], check=True)

    with open(source_code_pro_bold, 'rb') as f:
        woff_bold = base64.b64encode(f.read()).decode()

    svg.write(f"""<svg
    xmlns="http://www.w3.org/2000/svg"
    xmlns:xlink="http://www.w3.org/1999/xlink">

    <style>
        @font-face {{
            font-family: 'Source Code Pro';
            font-style: normal;
            font-weight: 400;
            src: url(data:application/font-woff;charset=utf-8;base64,{woff_normal}) format('woff2');
            unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
        }}
        @font-face {{
            font-family: 'Source Code Pro';
            font-style: normal;
            font-weight: 600;
            src: url(data:application/font-woff;charset=utf-8;base64,{woff_bold}) format('woff2');
            unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
        }}

""")

    svg.write("""
        svg {
            background-color: #2f363f;
        }
        text {
            font-family: Source Code Pro;
            white-space: pre;
            fill: #e6e6e6;
            dominant-baseline: hanging;
        }
        text a:hover {
            text-decoration: underline;
        }

        .hll { background-color: #34424d }
        .c { fill: #a5c9ea } /* Comment */
        .k { fill: #ffffff; font-weight: bold } /* Keyword */
        .n { fill: #dcdcdc } /* Name */
        .o { fill: #aaaaaa } /* Operator */
        .p { fill: #aaaaaa } /* Punctuation */
        .ch { fill: #a5c9ea } /* Comment.Hashbang */
        .cm { fill: #a5c9ea } /* Comment.Multiline */
        .cp { fill: #3bd267 } /* Comment.Preproc */
        .cpf { fill: #c7cf2f } /* Comment.PreprocFile */
        .c1 { fill: #a5c9ea } /* Comment.Single */
        .cs { fill: #a5c9ea } /* Comment.Special */
        .gd { fill: #cd3431 } /* Generic.Deleted */
        .ge { fill: #e6e6e6; font-style: italic } /* Generic.Emph */
        .gh { fill: #ffffff; font-weight: bold } /* Generic.Heading */
        .gi { fill: #3bd267 } /* Generic.Inserted */
        .gs { fill: #e6e6e6; font-weight: bold } /* Generic.Strong */
        .gu { fill: #5b9dd9 } /* Generic.Subheading */
        .kc { fill: #ffffff; font-weight: bold } /* Keyword.Constant */
        .kd { fill: #ffffff; font-weight: bold } /* Keyword.Declaration */
        .kn { fill: #ffffff; font-weight: bold } /* Keyword.Namespace */
        .kp { fill: #ffffff; font-weight: bold } /* Keyword.Pseudo */
        .kr { fill: #ffffff; font-weight: bold } /* Keyword.Reserved */
        .kt { fill: #ffffff; font-weight: bold } /* Keyword.Type */
        .m { fill: #c7cf2f } /* Literal.Number */
        .s { fill: #e07f7c } /* Literal.String */
        .na { fill: #dcdcdc; font-weight: bold } /* Name.Attribute */
        .nb { fill: #ffffff; font-weight: bold } /* Name.Builtin */
        .nc { fill: #dcdcdc; font-weight: bold } /* Name.Class */
        .no { fill: #dcdcdc } /* Name.Constant */
        .nd { fill: #dcdcdc } /* Name.Decorator */
        .ni { fill: #dcdcdc } /* Name.Entity */
        .ne { fill: #dcdcdc } /* Name.Exception */
        .nf { fill: #dcdcdc } /* Name.Function */
        .nl { fill: #dcdcdc } /* Name.Label */
        .nn { fill: #dcdcdc } /* Name.Namespace */
        .nx { fill: #dcdcdc } /* Name.Other */
        .py { fill: #dcdcdc } /* Name.Property */
        .nt { fill: #dcdcdc; font-weight: bold } /* Name.Tag */
        .nv { fill: #c7cf2f } /* Name.Variable */
        .ow { fill: #dcdcdc; font-weight: bold } /* Operator.Word */
        .mb { fill: #c7cf2f } /* Literal.Number.Bin */
        .mf { fill: #c7cf2f } /* Literal.Number.Float */
        .mh { fill: #c7cf2f } /* Literal.Number.Hex */
        .mi { fill: #c7cf2f } /* Literal.Number.Integer */
        .mo { fill: #c7cf2f } /* Literal.Number.Oct */
        .sa { fill: #e07f7c } /* Literal.String.Affix */
        .sb { fill: #e07f7c } /* Literal.String.Backtick */
        .sc { fill: #e07cdc } /* Literal.String.Char */
        .dl { fill: #e07f7c } /* Literal.String.Delimiter */
        .sd { fill: #e07f7c } /* Literal.String.Doc */
        .s2 { fill: #e07f7c } /* Literal.String.Double */
        .se { fill: #e07cdc } /* Literal.String.Escape */
        .sh { fill: #e07f7c } /* Literal.String.Heredoc */
        .si { fill: #a5c9ea } /* Literal.String.Interpol */
        .sx { fill: #e07f7c } /* Literal.String.Other */
        .sr { fill: #e07f7c } /* Literal.String.Regex */
        .s1 { fill: #e07f7c } /* Literal.String.Single */
        .ss { fill: #e07f7c } /* Literal.String.Symbol */
        .bp { fill: #ffffff; font-weight: bold } /* Name.Builtin.Pseudo */
        .fm { fill: #dcdcdc } /* Name.Function.Magic */
        .vc { fill: #c7cf2f } /* Name.Variable.Class */
        .vg { fill: #c7cf2f } /* Name.Variable.Global */
        .vi { fill: #c7cf2f } /* Name.Variable.Instance */
        .vm { fill: #c7cf2f } /* Name.Variable.Magic */
        .il { fill: #c7cf2f } /* Literal.Number.Integer.Long */
    </style>

    <text style="white-space: pre">""")

    offset = 0
    for tok in tokens:
        if tok['offset'] > offset:
            svg.write(html.escape(code[offset:tok['offset']].decode()))

        linked = 'link' in tok and 'cppref' in tok['link']
        if linked:
            svg.write(f'<a href="https://en.cppreference.com/w/{tok["link"]["cppref"]}">')

        css_class = TOKEN_TYPE_TO_CSS_CLASS.get(tok['type'], '')
        svg.write(f'<tspan class="{css_class}">')

        end = tok['offset'] + tok['length']
        svg.write(html.escape(code[tok['offset']:end].decode()))

        svg.write('</tspan>')

        if linked:
            svg.write('</a>')

        offset = end

    svg.write("</text>\n</svg>")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', type=str, help='Path to compilation db')
    parser.add_argument('--output', '-o', type=str, help='Output file', default='/dev/stdout')
    parser.add_argument('input', type=str, help='Input file')

    args = parser.parse_args()

    base = Path(__file__).parent
    ch = base.parent / 'build' / 'clang-highlight'

    with tempfile.TemporaryDirectory(delete=False) as build_dir:
        build_dir = Path(build_dir)

        stderr = None

        ch_args = [ch]

        if args.p:
            ch_args += ['-p', args.p]

        ch_args += ['--json-out', args.input]

        result = subprocess.run(ch_args,
                                stdout=subprocess.PIPE,
                                stderr=stderr,
                                check=True)

    with open(args.input, 'rb') as f:
        code = f.read()

    tokens = json.loads(result.stdout)["tokens"]

    # Load STL map
    with open(Path.home() / '.cache' / 'clang_highlight_stl.json') as f:
        stl_map = json.load(f)

    # Resolve STL tokens
    for tok in tokens:
        if 'link' in tok:
            link = tok['link']

            # First try: non-overloaded symbols
            page = stl_map['symbols'].get(link['qualified_name'])

            # Second try: some overload
            if page is None and 'parameter_types' in link:
                overloads = stl_map['overloads'].get(link['qualified_name'])
                if overloads is not None:
                    matching = [ o for o in overloads if overload_match(o['overload'], link) ]
                    if matching:
                        page = matching[0]['page']

            if page is not None:
                link['cppref'] = page


    with open(args.output, 'w') as f:
        produce_svg(tokens=tokens, code=code, svg=f)
