#!/bin/bash

set -euxo pipefail

if [[ -v GITHUB_WORKSPACE ]]; then
    cd "${GITHUB_WORKSPACE}"
else
    cd "/work"
fi

mkdir -p build_docker
cd build_docker
rm -Rf *

cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo -DLLVM_DIR=/llvm/lib/cmake/llvm ..

make
make test
