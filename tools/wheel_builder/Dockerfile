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
    -DLLVM_ENABLE_ZLIB=OFF \
    -DCMAKE_INSTALL_PREFIX=/opt/llvm \
    /llvm-src/llvm

RUN cmake --build /llvm-build
RUN cmake --install /llvm-build

FROM quay.io/pypa/manylinux_2_28_x86_64 AS final

COPY --from=build /opt/llvm/include /opt/llvm/include
COPY --from=build /opt/llvm/lib/*.a /opt/llvm/lib/
COPY --from=build /opt/llvm/lib/clang /opt/llvm/lib/clang
COPY --from=build /opt/llvm/bin/llvm-config /opt/llvm/bin/llvm-config

# clang 19 does not find the rh toolset (it has hardcoded paths for version <= 12)
RUN mkdir -p /etc/clang-highlight \
    && echo "--gcc-toolchain=/opt/rh/gcc-toolset-14/root" > /etc/clang-highlight/clang.cfg \
    && echo "--gcc-toolchain=/opt/rh/gcc-toolset-14/root" > /etc/clang-highlight/clang++.cfg

