"""
Maps from declarations of STL functions to their documentation on
cppreference.com.
"""

import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
import re
import tempfile
import json
import lxml.html
import sys
import dataclasses
from multiprocessing.pool import ThreadPool
from urllib.parse import quote

import requests
import shutil
import functools
from tqdm import tqdm

from .data import TokenType, HighlightedCode, Link
import clang_highlight

CACHE_FILE = Path.home() / ".cache" / "clang_highlight_stl.json"
DOWNLOAD_URL = "https://github.com/PeterFeicht/cppreference-doc/releases/download/v20241110/cppreference-doc-20241110.tar.xz"

header_regex = re.compile(r"header(=|\|)(?P<header>[^|}]+)(\||\})")
decl_regex = re.compile(r"\{\{dcla?\|.*\n((.*\n)+?)\}\}", re.MULTILINE)
whitespace_regex = re.compile(r"\s+")

signature_regex = re.compile(r"[^(]* (?P<name>[^ (]+)\s*\((?P<rest>.*)")

template_regex = re.compile(r"template\s*<(?P<rest>.*)")
template_type_arg_regex = re.compile(
    r"(class|typename|std::\w+<\w+>)\s*(?P<pack>(\.\.\.)?)\s*(?P<name>.*)"
)


def signature_split_rest(rest: str):
    """
    Get the parameter string ending with ")" out of the `rest` part matched
    in signature_regex. We assume this is well-formed C++ and thus we can
    just count opening and closing parentheses.

    Returns the parameter string and the rest of the rest.

    >>> signature_split_rest('int a, char b) const [[deprecated("reason")]];')
    ('int a, char b', ' const [[deprecated("reason")]];')
    """

    level = 1
    for idx, c in enumerate(rest):
        if c == "(":
            level += 1
        elif c == ")":
            level -= 1
            if level == 0:
                break

    assert level == 0

    return rest[:idx], rest[idx + 1 :]


def lex_params(params: str):
    """
    Stupid template parameter lexer

    >>> lex_params("class T, std::some_concept<parameters> b> void func()")
    (['class T', 'std::some_concept<parameters> b'], ' void func()')
    """
    ret = []
    current_param = ""
    level = 1

    for idx, c in enumerate(params):
        if level == 1:
            if c == ">":
                if current_param != "":
                    ret.append(current_param)
                end_idx = idx + 1
                break

            if c == ",":
                if current_param != "":
                    ret.append(current_param)
                current_param = ""
            else:
                current_param += c
        else:
            current_param += c

        if c == "<":
            level += 1
        elif c == ">":
            level -= 1

    assert level == 1
    return [p.strip() for p in ret], params[end_idx:]


def get_template_params(decl: str):
    """
    Get the template parameter list from a template declaration

    >>> get_template_params('template<class T, int c> func(T a, T b);')
    ['class T', 'int c']
    """
    tpl_match = template_regex.match(decl)

    if not tpl_match:
        return None

    params, _ = lex_params(tpl_match.group("rest"))
    return params


def forward_template_params(params):
    """
    Generate a template argument list that forwards all arguments from a parsed
    template parameter list.

    >>> params = get_template_params('template<class T, int c> func(T a, T b);')
    >>> forward_template_params(params)
    '<T, c>'
    """
    ret = []
    for p in params:
        if "=" in p:
            p, _, type = p.partition("=")
            p = p.strip()
            type = type.strip()

        name = p.rpartition(" ")[2]

        if "..." in p:
            ret.append(f"{name}...")
        else:
            ret.append(name)

    return f"<{', '.join(ret)}>"


def generate_template_args(params, exclude=set(), decl=""):
    """
    Tries to generate template arguments that make sense using heuristics.

    >>> params = get_template_params('template<class T, int c> func(T a, T b);')
    >>> args, typedefs, param_set = generate_template_args(params)
    >>> args
    '<int,0>'
    >>> typedefs
    ['using T = int;']
    >>> param_set
    {'T'}
    """

    typedefs = []
    args = []
    parameter_set = set()
    for p in params:
        is_default = False
        if "=" in p:
            is_default = True
            p, _, type = p.partition("=")
            p = p.strip()
            type = type.strip()

        type_arg_match = template_type_arg_regex.match(p)
        if type_arg_match:
            name = type_arg_match.group("name")

            if not is_default:
                type = "int"
                if name == "InputIt":
                    type = "iterator"
                elif name == "P":
                    type = "value_type"
                elif name == "C2":
                    type = "key_compare"
                elif name == "CharT":
                    type = "char"
                elif name == "Ostream":
                    type = "std::basic_ostream<char>"
                elif name == "Istream":
                    type = "std::basic_istream<char>"
                elif name == "Alloc":
                    if "Allocator" in exclude:
                        type = "Allocator"
                elif name == "Pred":
                    type = "MyPred"
                elif name == "U":
                    type = "char"
                elif name in ("T2", "U2"):
                    type = "char"
                elif name == "Traits":
                    type = "std::char_traits<char>"
                elif name == "Clock":
                    type = "std::chrono::high_resolution_clock"
                elif name == "ToDuration":
                    type = "std::chrono::seconds"
                elif name == "Duration":
                    type = "std::chrono::seconds"
                elif name == "C":
                    type = "std::chrono::high_resolution_clock"
                elif "Period" in name:
                    type = "std::ratio<1>"
                elif name == "P1":
                    type = "std::ratio<1>"
                elif name in ("D1", "D2"):
                    if "Deleter" in exclude:
                        type = "Deleter"
                    else:
                        type = "std::chrono::seconds"
                elif name == "P2":
                    type = "std::ratio<1>"
                elif name == "UIntType":
                    type = "unsigned int"
                elif name == "T" and "std::complex" in decl:
                    type = "double"
                elif name == "NonComplex":
                    type = "double"
                elif name == "T" and "Istream" in decl and "T&& value" in decl:
                    type = "int&"

                args.append(type)

            if name not in exclude:
                typedefs.append(f"using {name} = {type};")
                parameter_set.add(name)
        else:
            if "basic_istream" in decl:
                args.append("1")
            else:
                args.append("0")

    return f"<{','.join(args)}>", typedefs, parameter_set


def handle_class(cls: ET.Element, reference_base: Path, out_base: Path):
    pages = {}
    functions = {}

    if "/experimental/" in cls.attrib["link"]:
        return

    try:
        class_tree = lxml.html.fromstring(
            open(reference_base / f"{cls.attrib['link']}.html").read()
        )
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
    class_decl = whitespace_regex.sub(" ", class_decl)
    class_decl = class_decl.strip()

    # ... and parse it
    if "class" not in class_decl and "struct" not in class_decl:
        # print(
        #     f"class decl '{class_decl}' does not contain 'struct' or 'class'",
        #     file=sys.stderr)
        return

    tpl_params = get_template_params(class_decl)

    # Overloads of external functions
    for overload in cls.findall("overload"):
        link = overload.attrib.get("link", overload.attrib["name"])

        if link == ".":
            link = cls.attrib["link"]
        else:
            link = cls.attrib["link"] + "/" + link

        pages.setdefault(link, set()).add(overload.attrib["name"])

    for page, page_overloads in sorted(pages.items()):
        try:
            page_tree = lxml.html.fromstring(
                open(reference_base / f"{page}.html").read()
            )
        except FileNotFoundError:
            print(f"Warning: Page {page} not found", file=sys.stderr)
            continue

        content = page_tree.get_element_by_id("mw-content-text")

        # Find declarations
        for row in content.xpath(
            './/tr[contains(concat(" ",normalize-space(@class)," "), " t-dcl ")]'
        ):
            cell = row.find("./td[1]")
            assert cell is not None

            since_version = 1
            until_version = 99
            for css_cls in row.attrib["class"].split(" "):
                if css_cls.startswith("t-since-cxx"):
                    since_version = int(css_cls[11:])
                elif css_cls.startswith("t-until-cxx"):
                    until_version = int(css_cls[11:])

            if since_version > 23 or until_version <= 23:
                continue

            verbatim_code = cell.text_content()

            for verbatim_decl in verbatim_code.split(";"):
                decl = whitespace_regex.sub(" ", verbatim_decl).strip()
                if not decl:
                    continue

                # Text fragment directives do not work across block tag
                # boundaries. So extract the last line.
                fragment = verbatim_decl.rpartition("\n")[2].strip()

                functions[decl] = (page, fragment)

    if not functions:
        return

    # How do we instantiate this thing?
    cls_type = cls.attrib["name"]
    namespaces = cls_type.split("::")[:-1]
    typedefs = []
    tpl_parameter_set = set()
    if tpl_params:
        tpl_args, typedefs, tpl_parameter_set = generate_template_args(tpl_params)
        cls_type += tpl_args

    typedef_str = "\n    ".join(typedefs)
    out = f"""

#define static_assert(...)

#include {header}
#include <utility>
#include <tuple>

#pragma GCC diagnostic ignored "-Wreturn-type"
#pragma GCC diagnostic ignored "-Wunused-local-typedef"

template<typename T>
typename std::add_rvalue_reference<T>::type my_declval() noexcept
{{
}}

template<typename Sig>
struct Signature;

template<typename R, typename ...Args>
struct Signature<R(*)(Args...)>
{{
    using ArgTuple = std::tuple<Args...>;
    static constexpr std::size_t ArgCount = sizeof...(Args);

    template<std::size_t N>
    using ArgType = decltype(std::get<N>(my_declval<ArgTuple>()));

    template<std::size_t N>
    static ArgType<N> arg() noexcept
    {{}}
}};

struct MyPred {{
    bool operator()(auto) {{ return true; }}
}};

{" ".join(["namespace " + ns + " {" for ns in namespaces])}
{typedef_str}
using MyType = {cls_type};

"""

    num = 0
    for decl, page_and_fragment in functions.items():
        page, fragment = page_and_fragment
        if "= delete" in decl:
            continue

        # Not a function?
        if "(" not in decl:
            continue

        num += 1
        decl_tpl_params = get_template_params(decl)
        decl_tpl_forward = ""
        decl_typedefs = []
        decl_tpl_args = ""
        decl_tpl_decl = ""
        if decl_tpl_params:
            decl_tpl_args, decl_typedefs, _ = generate_template_args(
                decl_tpl_params, exclude=tpl_parameter_set, decl=decl
            )
            decl_tpl_decl = f"template <{', '.join(decl_tpl_params)}>"
            decl_tpl_forward = forward_template_params(decl_tpl_params)

        name_match = signature_regex.match(decl)

        if name_match:
            name = name_match.group("name")
            rest = name_match.group("rest")

            param_str, rest_after_params = signature_split_rest(rest)

            if name.startswith("operator"):
                # Operators rarely need explicit template arguments, and this is
                # an area where cppreference deviates from the GNU STL quite a
                # lot (e.g. std::pair's operator== overload).
                decl_tpl_forward = ""

            if "friend " in decl:
                # If this is a friend function declaration, it is declared
                # inside the class and thus can use the class name to refer
                # to the specific template instantiation. We emulate that
                # by declaring a local typedef.
                local_name = cls.attrib["name"].rpartition("::")[2]
                local_typedef = f"using {local_name} = MyType;"
            else:
                local_typedef = ""

            call = f"""{decl_tpl_decl}
    struct Call{num} {{
        {local_typedef}
        static void signature({param_str});
        void call()
        {{
            using Sig = Signature<decltype(&signature)>;
            []<auto... Is>(const std::index_sequence<Is...>&){{
                static_cast<void>(/* -> */ {name}{decl_tpl_forward}(Sig::template arg<Is>()...));
            }}(std::make_index_sequence<Sig::ArgCount>());
        }}
    }};"""

            # Add an explicit instantiation with the declared template arguments
            if decl_tpl_decl:
                call += f"""
    template struct Call{num}{decl_tpl_args};"""
        else:
            call = ""
            # call = decl

        frag_directive = f"#:~:text={quote(fragment)}"
        out += f"""
    // PAGE: {page}{frag_directive}
    // {decl}
    {call}
"""

    out += f"""
{"".join(["}" for ns in namespaces])}
"""

    out_path = out_base / (cls.attrib["link"] + ".cpp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(out)

    return out_path


def process_file(path: Path):
    highlighted = clang_highlight.run(filename=path)

    ret = []
    num_page_comments = 0
    take_next = False
    current_page = None

    for text, token in highlighted:
        if not token:
            continue

        if take_next:
            if token.link:
                ret.append(
                    {
                        "page": current_page,
                        "overload": dataclasses.asdict(token.link),
                    }
                )

            take_next = False
            continue

        if token.type == TokenType.COMMENT:
            if text.startswith("// PAGE: "):
                current_page = text[9:].strip()
                num_page_comments += 1

            elif text == "/* -> */":
                take_next = True

    return ret, (num_page_comments - len(ret))


def get_symbols(index: ET.ElementTree):
    symbols = {}

    alias_symbols = {}

    # Global things
    for thing in ("typedef", "const", "function"):
        for t in index.findall(thing):
            try:
                symbols[t.attrib["name"]] = t.attrib["link"]
            except KeyError:
                if "alias" in t.attrib:
                    alias_symbols[t.attrib["name"]] = t.attrib["alias"]
                else:
                    print(f"Thing {t.attrib['name']} has no link!", file=sys.stderr)

    # Classes
    for cls in index.findall("class"):
        cls_name = cls.attrib["name"]
        cls_name_local = cls_name.rpartition("::")[2]
        cls_link = cls.attrib["link"]
        symbols[cls_name] = cls_link

        def link(t, tn=None):
            if not tn:
                tn = t.attrib["name"]
            tl = t.attrib.get("link", f"{cls_link}/{tn}")
            if tl == ".":
                return cls_link
            else:
                return tl

        for thing in ("typedef", "const", "function"):
            for t in cls.findall(thing):
                t_name = f"{cls_name}::{t.attrib['name']}"
                symbols[t_name] = link(t)

        cons = cls.find("constructor")
        if cons is not None:
            symbols[f"{cls_name}::{cls_name_local}"] = link(cons, cls_name_local)

        des = cls.find("destructor")
        if des is not None:
            symbols[f"{cls_name}::~{cls_name_local}"] = link(des, cls_name_local)

    for name, to in alias_symbols.items():
        symbols[name] = symbols[to]

    return symbols


def get_headers(reference_base: Path):
    # I'd love to use index-chapters-cpp.xml, but it's not complete.
    tree = lxml.html.fromstring(open(reference_base / "cpp" / "headers.html").read())

    xml_headers = tree.findall(".//div[@class='t-dsc-member-div']//a")
    headers = {}
    link_re = re.compile(r"header/(?P<name>.*)\.html")
    for a in xml_headers:
        m = link_re.match(a.attrib["href"])
        assert m is not None, f"Could not match {a.attrib['href']}"
        headers[f"<{m['name']}>"] = f"cpp/header/{m['name']}"

    code = "\n".join([f"#include {n}" for n in headers.keys()])

    h = clang_highlight.run(code=code)

    include_to_link = {}

    for text, token in h:
        if not token or token.type != TokenType.PREPROCESSOR_FILE:
            continue

        if token.link:
            include_to_link[str(token.link.file)] = headers[text]

    return include_to_link


def work(workdir: Path):
    archive_path = workdir / "cppreference.tar.xz"

    if not archive_path.exists():
        print("Downloading cppreference archive", file=sys.stderr)

        response = requests.get(DOWNLOAD_URL, stream=True, allow_redirects=True)

        if response.status_code != 200:
            response.raise_for_status()
            raise RuntimeError(
                f"Got HTTP {response.status_code} while trying to download {DOWNLOAD_URL}"
            )

        total_size = int(response.headers.get("content-length", 0))

        desc = "(Unknown total file size)" if total_size == 0 else ""

        response.raw.read = functools.partial(response.raw.read, decode_content=True)
        with tqdm.wrapattr(response.raw, "read", total=total_size, desc=desc) as r_raw:
            with archive_path.open("wb") as f:
                shutil.copyfileobj(r_raw, f)

    extracted_path = workdir / "cppreference"
    if not (extracted_path / "Makefile").exists():
        print("Extracting...", file=sys.stderr)
        extracted_path.mkdir(exist_ok=True)

        subprocess.run(
            [
                "tar",
                "-C",
                extracted_path,
                "-x",
                "--strip-components=1",
                "-f",
                archive_path.absolute(),
            ],
            check=True,
        )

    reference_base = extracted_path / "reference" / "en.cppreference.com" / "w"

    print("\nMapping headers...\n", file=sys.stderr)
    headers = get_headers(reference_base)

    tree = ET.parse(extracted_path / "index-functions-cpp.xml")
    symbols = get_symbols(tree)

    out_base = workdir / "stl_calls"
    out_base.mkdir(exist_ok=True)

    print("\nGenerating STL calls...\n", file=sys.stderr)
    files = []
    for cls in tree.findall("class"):
        f = handle_class(cls, reference_base, out_base)
        if f:
            files.append(f)

    print("\nResolving STL calls...", file=sys.stderr)
    pool = ThreadPool()
    result = list(tqdm(pool.imap(lambda x: process_file(x), files), total=len(files)))

    result = list(zip(files, result))
    result = sorted(result, key=lambda x: x[1][1])

    print("STL mapping failures per file:", file=sys.stderr)
    for f, res in result:
        if res[1] != 0:
            print(f, res[1], file=sys.stderr)

    print(f"Failures in total: {sum([res[1][1] for res in result])}", file=sys.stderr)

    functions = {}
    for f, res in result:
        infos = res[0]
        for info in infos:
            functions.setdefault(info["overload"]["qualified_name"], []).append(info)

    def serialize_path(p):
        if isinstance(p, Path):
            return str(p)

        raise TypeError(f"Invalid type for JSON: {type(p)}")

    with open(CACHE_FILE, "w") as f:
        json.dump(
            {"symbols": symbols, "overloads": functions, "headers": headers},
            f,
            indent=2,
            default=serialize_path,
        )


def overload_match(overload: dict, link: Link):
    if overload["qualified_name"] != link.qualified_name:
        return False

    if overload["parameter_types"] != link.parameter_types:
        return False

    return True


def resolve_stl(highlighted: HighlightedCode):
    if not CACHE_FILE.exists():
        with tempfile.TemporaryDirectory(prefix="stl_map") as workdir:
            work(Path(workdir))

    # Load STL map
    with open(Path.home() / ".cache" / "clang_highlight_stl.json") as f:
        stl_map = json.load(f)

    # Resolve STL tokens
    for tok in highlighted.tokens:
        if not tok.link:
            continue

        link = tok.link

        # First try: non-overloaded symbols
        page = stl_map["symbols"].get(link.qualified_name)

        # Second try: some overload
        if page is None and link.parameter_types is not None:
            overloads = stl_map["overloads"].get(tok.link.qualified_name)
            if overloads is not None:
                matching = [o for o in overloads if overload_match(o["overload"], link)]
                if matching:
                    page = matching[0]["page"]

        # Is this a header?
        if link.name == "<file>":
            page = stl_map["headers"].get(str(link.file))

        if page is not None:
            link.cppref = page


if __name__ == "__main__":
    import sys

    workdir = Path(sys.argv[1])
    workdir.mkdir(exist_ok=True)
    work(workdir)
