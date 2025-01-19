FROM quay.io/pypa/manylinux_2_28_x86_64 AS build

# Install recent version of ninja
RUN mkdir /ninja-src
RUN curl -L 'https://github.com/ninja-build/ninja/archive/refs/tags/v1.12.1.tar.gz' | tar -C /ninja-src --strip-components=1 -z -x
RUN mkdir /ninja-build
RUN cd /ninja-build && cmake -DCMAKE_BUILD_TYPE=Release /ninja-src
RUN cd /ninja-build && make -j4 install


RUN mkdir /llvm-src

RUN curl -L 'https://github.com/llvm/llvm-project/releases/download/llvmorg-19.1.0/llvm-project-19.1.0.src.tar.xz' | xz -d | tar -C /llvm-src --strip-components=1 -x

RUN mkdir /llvm-build

RUN cd /llvm-build && cmake -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLVM_ENABLE_PROJECTS="clang" \
    -DLLVM_PARALLEL_LINK_JOBS=4 \
    -DLLVM_TARGETS_TO_BUILD="X86" \
    -DCMAKE_INSTALL_PREFIX=/opt/llvm \
    /llvm-src/llvm

RUN cmake --build /llvm-build
RUN cmake --install /llvm-build

FROM quay.io/pypa/manylinux_2_28_x86_64 AS final

COPY --from=build /opt/llvm/include /opt/llvm/include
COPY --from=build /opt/llvm/lib/*.a /opt/llvm/lib/
COPY --from=build /opt/llvm/lib/clang /opt/llvm/lib/clang
COPY --from=build /opt/llvm/bin/llvm-config /opt/llvm/bin/llvm-config
