#!/usr/bin/env python
"""
Maps from declarations of STL functions to their documentation on
cppreference.com.
"""

DOWNLOAD_URL = "https://github.com/PeterFeicht/cppreference-doc/releases/download/v20241110/cppreference-doc-20241110.tar.xz"

import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
import re
import tempfile
import json
import lxml.html
import sys
# import html5lib

from typing import Dict

header_regex = re.compile(r'header(=|\|)(?P<header>[^|}]+)(\||\})')
decl_regex = re.compile(r'\{\{dcla?\|.*\n((.*\n)+?)\}\}', re.MULTILINE)
whitespace_regex = re.compile(r'\s+')

signature_regex = re.compile(r'[^(]* (?P<name>[^ (]+)\s*\((?P<rest>.*)')

template_regex = re.compile(r'template\s*<(?P<rest>.*)')
template_type_arg_regex = re.compile(r'(class|typename|std::\w+<\w+>)\s*(?P<pack>(\.\.\.)?)\s*(?P<name>.*)')



def get_type(param: str):
    """
    Get type out of a parameter like "int a"
    """
    if ' ' in param:
        return param.strip().rpartition(' ')[0]

    return param.strip()


def lex_params(params: str, end: str = ')'):
    # Stupid params lexer
    ret = []
    current_param = ''
    level = 1

    for idx, c in enumerate(params):
        if level == 1:
            if c == end:
                if current_param != '':
                    ret.append(current_param)
                end_idx = idx + 1
                break

            if c == ',':
                if current_param != '':
                    ret.append(current_param)
                current_param = ''
            else:
                current_param += c
        else:
            current_param += c

        if c == '<':
            level += 1
        elif c == '>':
            level -= 1

    assert level == 1
    return [p.strip() for p in ret], params[end_idx:]


def get_template_params(decl: str):
    tpl_match = template_regex.match(decl)

    if not tpl_match:
        return None

    # Stupid template params lexer
    params, _ = lex_params(tpl_match.group('rest'), '>')
    # print(f"{decl} -> {tpl_match.group('rest')} -> {params}")
    return params

def forward_template_params(params):
    ret = []
    for p in params:
        is_default = False
        if '=' in p:
            is_default = True
            p, _, type = p.partition('=')
            p = p.strip()
            type = type.strip()

        name = p.rpartition(' ')[2]

        if '...' in p:
            ret.append(f"{name}...")
        else:
            ret.append(name)

    return f"<{', '.join(ret)}>"


def generate_template_args(params, exclude=set(), only_non_type=False):
    typedefs = []
    args = []
    parameter_set = set()
    for p in params:
        is_default = False
        if '=' in p:
            is_default = True
            p, _, type = p.partition('=')
            p = p.strip()
            type = type.strip()

        type_arg_match = template_type_arg_regex.match(p)
        if type_arg_match:
            name = type_arg_match.group('name')

            if not is_default:
                type = 'int'
                if name == 'InputIt':
                    type = 'iterator'
                elif name == 'P':
                    type = 'value_type'
                elif name == 'C2':
                    type = 'key_compare'
                elif name == 'CharT':
                    type = 'char'
                elif name == 'Ostream':
                    type = 'std::basic_ostream<char>'
                elif name == 'Alloc':
                    if 'Allocator' in exclude:
                        type = 'Allocator'
                elif name == 'Pred':
                    type = 'MyPred'
                elif name == 'U':
                    type = 'char'
                elif name in ('T2', 'U2'):
                    type = 'char'
                elif name == 'Traits':
                    type = 'std::char_traits<char>'
                elif name == 'Clock':
                    type = 'std::chrono::high_resolution_clock'
                elif name == 'ToDuration':
                    type = 'std::chrono::seconds'
                elif name == 'Duration':
                    type = 'std::chrono::seconds'
                elif name == 'C':
                    type = 'std::chrono::high_resolution_clock'
                elif 'Period' in name:
                    type = 'std::ratio<1>'
                elif name == 'P1':
                    type = 'std::ratio<1>'
                elif name in ('D1', 'D2'):
                    if 'Deleter' in exclude:
                        type = 'Deleter'
                    else:
                        type = 'std::chrono::seconds'
                elif name == 'P2':
                    type = 'std::ratio<1>'

                if not only_non_type:
                    args.append(type)

            if name not in exclude:
                typedefs.append(f"using {name} = {type};")
                parameter_set.add(name)
        else:
            args.append('0')

    return f"<{','.join(args)}>", typedefs, parameter_set


def handle_class(cls: ET.Element, reference_base: Path, out_base: Path):
    pages = {}
    functions = {}

    if '/experimental/' in cls.attrib['link']:
        return

    try:
        class_tree = lxml.html.fromstring(
            open(reference_base / f"{cls.attrib['link']}.html").read())
    except FileNotFoundError:
        return

    # Find header
    header = class_tree.find('.//tr[@class="t-dsc-header"]//code')
    if header is None:
        print(f"No header for {cls.attrib['link']}", file=sys.stderr)
        return
    header = header.text_content()

    # Find class/struct declaration
    class_decl = class_tree.xpath(
        './/tr[contains(concat(" ",normalize-space(@class)," "), " t-dcl ")]/td[1]'
    )
    if not class_decl:
        print(f"No class decl for {cls.attrib['link']}", file=sys.stderr)
        return
    class_decl = class_decl[0].text_content()
    class_decl = whitespace_regex.sub(' ', class_decl)
    class_decl = class_decl.strip()

    # ... and parse it
    if 'class' not in class_decl and 'struct' not in class_decl:
        print(
            f"class decl '{class_decl}' does not contain 'struct' or 'class'",
            file=sys.stderr)
        return

    tpl_params = get_template_params(class_decl)

    # Overloads of external functions
    for overload in cls.findall('overload'):
        link = overload.attrib.get('link', overload.attrib['name'])

        if link == '.':
            link = cls.attrib['link']
        else:
            link = cls.attrib['link'] + '/' + link

        pages.setdefault(link, set()).add(overload.attrib['name'])

    # print(pages)

    for page, page_overloads in sorted(pages.items()):
        try:
            page_tree = lxml.html.fromstring(
                open(reference_base / f"{page}.html").read())
        except FileNotFoundError:
            print(f"Warning: Page {page} not found", file=sys.stderr)
            continue

        content = page_tree.get_element_by_id('mw-content-text')

        # Find declarations
        for row in content.xpath(
                './/tr[contains(concat(" ",normalize-space(@class)," "), " t-dcl ")]'
        ):
            cell = row.find('./td[1]')
            assert cell is not None

            since_version = 1
            until_version = 99
            for css_cls in row.attrib['class'].split(' '):
                if css_cls.startswith('t-since-cxx'):
                    since_version = int(css_cls[11:])
                elif css_cls.startswith('t-until-cxx'):
                    until_version = int(css_cls[11:])

            if since_version > 23 or until_version <= 23:
                continue

            code = cell.text_content()
            code = whitespace_regex.sub(' ', code)

            # if not any([ (ov in code) for ov in page_overloads ]):
            #     print(f"Skipping {code}")
            #     continue

            for decl in code.split(';'):
                decl = decl.strip()
                if not decl:
                    continue

                functions[decl] = page

    if not functions:
        return

    # How do we instantiate this thing?
    cls_type = cls.attrib['name']
    namespaces = cls_type.split('::')[:-1]
    typedefs = []
    tpl_parameter_set = set()
    if tpl_params:
        tpl_args, typedefs, tpl_parameter_set = generate_template_args(
            tpl_params)
        cls_type += tpl_args

    out = f"""
#include {header}
#include <utility>

#pragma GCC diagnostic ignored "-Wreturn-type"
#pragma GCC diagnostic ignored "-Wunused-local-typedef"

template<typename T>
typename std::add_rvalue_reference<T>::type my_declval() noexcept
{{
}}

struct MyPred {{
    bool operator()(auto) {{ return true; }}
}};

{' '.join(["namespace " + ns + " {" for ns in namespaces]) }
{'\n    '.join(typedefs)}
using MyType = {cls_type};

"""

    num = 0
    for decl, page in functions.items():
        if '= delete' in decl:
            continue

        num += 1
        decl_tpl_params = get_template_params(decl)
        decl_tpl_forward = ''
        decl_typedefs = []
        decl_tpl_args = ''
        decl_tpl_decl = ''
        if decl_tpl_params:
            decl_tpl_args, decl_typedefs, _ = generate_template_args(
                decl_tpl_params, exclude=tpl_parameter_set)
            decl_tpl_decl = f"template <{', '.join(decl_tpl_params)}>"
            decl_tpl_forward = forward_template_params(decl_tpl_params)

        name_match = signature_regex.match(decl)

        if name_match:
            name = name_match.group('name')
            rest = name_match.group('rest')

            params, rest = lex_params(rest)

            # # ignore argument packs
            # params = [p for p in params if '...' not in p]

            # ignore defaulted parameters
            params = [p for p in params if '=' not in p]

            # extract type
            params = [get_type(p) for p in params if len(p.strip()) != 0]

            params = [f"my_declval<{p}>()" for p in params]

            if name.startswith('operator'):
                # Operators rarely need explicit template arguments, and this is
                # an area where cppreference deviates from the GNU STL quite a
                # lot (e.g. std::pair's operator== overload).
                decl_tpl_forward = ''

            # call = f"static_cast<void>(/* -> */ {name}{decl_tpl_args}({', '.join(params)}));"

            call = f"""{decl_tpl_decl}
    void call{num}() {{"""

            if 'friend ' in decl:
                local_name = cls.attrib['name'].rpartition('::')[2]
                call += f"\n        using {local_name} = MyType;"

            call += f"""
        static_cast<void>(/* -> */ {name}{decl_tpl_forward}({', '.join(params)}));
    }}"""

            if decl_tpl_decl:
                call += f"""
    template void call{num}{decl_tpl_args}();"""
        else:
            call = ""
            # call = decl

        out += f"""
    // PAGE: {page}
    // {decl}
    { call }
"""

    out += f"""
{''.join(["}" for ns in namespaces]) }
"""

    out_path = out_base / (cls.attrib['link'] + '.cpp')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(out)


if __name__ == "__main__":
    base = Path(__file__).parent

    archive_path = base / 'cppreference.tar.xz'
    if not archive_path.exists():
        print('Downloading cppreference archive')
        subprocess.run(['wget', DOWNLOAD_URL, f'-O{archive_path}'], check=True)

    extracted_path = base / 'cppreference'
    if not (extracted_path / 'Makefile').exists():
        print('Extracting...')
        extracted_path.mkdir(exist_ok=True)

        subprocess.run([
            'tar', '-C', extracted_path, '-x', '--strip-components=1', '-f',
            archive_path.absolute()
        ],
                       check=True)

    tree = ET.parse(extracted_path / 'index-functions-cpp.xml')

    reference_base = extracted_path / 'reference' / 'en.cppreference.com' / 'w'

    out_base = base / 'stl_calls'
    out_base.mkdir(exist_ok=True)

    for cls in tree.findall('class'):
        handle_class(cls, reference_base, out_base)
