FROM ubuntu:24.04

RUN apt-get update && apt-get -y install wget build-essential cmake libzstd-dev zlib1g-dev python-is-python3 python3 && rm -rf /var/cache/apt/archives /var/lib/apt/lists

RUN echo deb http://apt.llvm.org/noble/ llvm-toolchain-noble main > /etc/apt/sources.list.d/llvm.list
RUN wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key > /etc/apt/trusted.gpg.d/apt.llvm.org.asc

ARG LLVM_VERSION=20

RUN apt-get update && apt-get -y install \
    libclang-${LLVM_VERSION}-dev llvm-${LLVM_VERSION}-dev \
    && rm -rf /var/cache/apt/archives /var/lib/apt/lists

RUN ln -s /usr/lib/llvm-${LLVM_VERSION} /llvm
