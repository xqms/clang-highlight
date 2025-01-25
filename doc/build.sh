#!/bin/bash

set -e

DIR="$(dirname "$0")"

if [[ ! -e "$DIR/m.css" ]]; then
  git clone https://github.com/mosra/m.css.git "$DIR/m.css"
fi

clang-highlight -f html_embed --cppref "$DIR/example.cpp" > "$DIR/example.html"

"$DIR/m.css/documentation/python.py" "$DIR/conf.py"
