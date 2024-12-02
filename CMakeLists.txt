
cmake_minimum_required(VERSION 3.20)
project(clang_highlight)

set(CMAKE_CXX_STANDARD 23)

find_package(LLVM REQUIRED)
message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")


function(find_clang_lib name)
    find_library(clang_${name} clang${name} PATHS ${LLVM_LIBRARY_DIRS})

    add_library(clang${name} INTERFACE)
    target_include_directories(clang${name} SYSTEM INTERFACE ${LLVM_INCLUDE_DIRS})
    target_link_libraries(clang${name} INTERFACE ${clang_${name}})
    add_library(clang::${name} ALIAS clang${name})
endfunction()

function(find_llvm_lib name)
    llvm_map_components_to_libnames(llvm_libs ${name})

    add_library(llvm${name} INTERFACE)
    target_include_directories(llvm${name} SYSTEM INTERFACE ${LLVM_INCLUDE_DIRS})
    target_link_libraries(llvm${name} INTERFACE ${llvm_libs})
    add_library(llvm::${name} ALIAS llvm${name})
endfunction()

find_clang_lib(Analysis)
find_clang_lib(AST)
find_clang_lib(ASTMatchers)
find_clang_lib(Basic)
find_clang_lib(Driver)
find_clang_lib(Edit)
find_clang_lib(APINotes)
find_clang_lib(Frontend)
find_clang_lib(Serialization)
find_clang_lib(Sema)
find_clang_lib(Lex)
find_clang_lib(Parse)
find_clang_lib(Tooling)
find_clang_lib(Support)

find_llvm_lib(Core)
find_llvm_lib(Support)
find_llvm_lib(Option)
find_llvm_lib(ProfileData)
find_llvm_lib(FrontendOpenMP)
find_llvm_lib(WindowsDriver)

add_executable(clang_highlight
    clang_highlight.cpp
)
target_link_libraries(clang_highlight PRIVATE
    clang::Frontend
    clang::Parse
    clang::Sema
    clang::Serialization
    clang::AST
    clang::Tooling
    clang::Driver
    clang::Edit
    clang::Lex
    clang::APINotes
    clang::Analysis
    clang::ASTMatchers
    clang::Basic
    clang::Support
    llvm::Core
    llvm::Option
    llvm::Support
    llvm::ProfileData
    llvm::FrontendOpenMP
    llvm::WindowsDriver
)
