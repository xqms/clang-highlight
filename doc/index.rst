clang-highlight
===============

What is this?
-------------

clang-highlight reads C/C++ code and outputs semantic tokens that can be used
for syntax highlighting and interactive links. It is able to understand your
code perfectly since it uses clang to lex the input and generate an AST.

This tool is meant for static use cases (e.g. code documentation) rather than
interactive use.

Here is an example output:

.. raw:: html
    :file: example.html

Tip: Nearly all tokens are linked to documentation or sources.

Compare that with `Pygments https://pygments.org/`_' output:

.. include:: example.cpp
    :code: c++
