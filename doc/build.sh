#!/bin/bash

set -e

DIR="$(dirname "$0")"

if [[ ! -e "$DIR/m.css" ]]; then
  git clone https://github.com/mosra/m.css.git "$DIR/m.css"
fi

"$DIR/m.css/documentation/python.py" "$DIR/conf.py"
