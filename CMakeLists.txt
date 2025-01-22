
cmake_minimum_required(VERSION 3.20)
project(clang_highlight)

# If we are run by scikit-build-core, use their project version. Otherwise,
# use the last git tag.
if(DEFINED SKBUILD_PROJECT_VERSION)
    set(VERSION_STRING "${SKBUILD_PROJECT_VERSION}")
else()
    include(cmake/GitVersion.cmake)
endif()

if(VERSION_STRING MATCHES "[vV]?([0-9]+)\\.([0-9]+)\\.([0-9]+)")
    set(VERSION_MAJOR ${CMAKE_MATCH_1})
    set(VERSION_MINOR ${CMAKE_MATCH_2})
    set(VERSION_PATCH ${CMAKE_MATCH_3})
else()
    set(VERSION_MAJOR 0)
    set(VERSION_MINOR 0)
    set(VERSION_PATCH 0)
    message(WARNING "Failed to determine version from scikit-core-build or Git tags (\"${VERSION_STRING}\"). Using default version \"${VERSION_MAJOR}.${VERSION_MINOR}.${VERSION_PATCH}\".")
endif()

set(CMAKE_CXX_STANDARD 23)

if(DEFINED ENV{LLVM_DIR})
    set(LLVM_BIN_DIR $ENV{LLVM_DIR}/bin)
endif()

find_program(LLVM_CONFIG llvm-config HINTS
    "/usr/lib/llvm-20/bin"
    "/usr/lib/llvm-19/bin"
    "/usr/lib/llvm-18/bin"
    "${LLVM_BIN_DIR}"
    REQUIRED
)

function(llvm_config output_var)
    execute_process(
        COMMAND ${LLVM_CONFIG} ${ARGN}
        OUTPUT_VARIABLE output
        COMMAND_ERROR_IS_FATAL ANY
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    set(${output_var} ${output} PARENT_SCOPE)
endfunction()

llvm_config(LLVM_VERSION --version)
message(STATUS "Found LLVM version ${LLVM_VERSION}")

string(REGEX MATCH "^([0-9]+)\\.([0-9]+)\\.([0-9]+)"
       LLVM_VERSION_MATCH ${LLVM_VERSION})
set(LLVM_VERSION_MAJOR ${CMAKE_MATCH_1})
set(LLVM_VERSION_MINOR ${CMAKE_MATCH_2})
set(LLVM_VERSION_PATCH ${CMAKE_MATCH_3})

llvm_config(LLVM_INCLUDE_DIR --includedir)
message(STATUS "LLVM include dir: ${LLVM_INCLUDE_DIR}")
llvm_config(LLVM_LIBRARY_DIR --libdir)
message(STATUS "LLVM library dir: ${LLVM_LIBRARY_DIR}")
llvm_config(LLVM_SYS_LIBS --link-static --system-libs)
separate_arguments(LLVM_SYS_LIBS UNIX_COMMAND ${LLVM_SYS_LIBS})
message(STATUS "LLVM system libs: ${LLVM_SYS_LIBS}")

function(find_clang_lib name)
    find_library(clang_${name} clang${name} PATHS ${LLVM_LIBRARY_DIR})

    add_library(clang${name} INTERFACE)
    target_include_directories(clang${name} SYSTEM INTERFACE ${LLVM_INCLUDE_DIR})
    target_link_libraries(clang${name} INTERFACE ${clang_${name}})
    add_library(clang::${name} ALIAS clang${name})
endfunction()

llvm_config(LLVM_LIBS_RAW --link-static --libnames Core Support Option ProfileData FrontendOpenMP WindowsDriver)
separate_arguments(LLVM_LIBS_RAW UNIX_COMMAND ${LLVM_LIBS_RAW})

add_library(llvm_libs INTERFACE)
target_include_directories(llvm_libs SYSTEM INTERFACE ${LLVM_INCLUDE_DIR})
foreach(lib ${LLVM_LIBS_RAW})
    target_link_libraries(llvm_libs INTERFACE ${LLVM_LIBRARY_DIR}/${lib})
endforeach()
target_link_libraries(llvm_libs INTERFACE ${LLVM_SYS_LIBS})
add_library(llvm::libs ALIAS llvm_libs)

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

add_executable(clang-highlight
    src/clang_highlight.cpp
)
target_compile_definitions(clang-highlight PRIVATE
    CH_VERSION_MAJOR=${VERSION_MAJOR}
    CH_VERSION_MINOR=${VERSION_MINOR}
    CH_VERSION_PATCH=${VERSION_PATCH}
)
target_compile_options(clang-highlight PRIVATE
    "-Wall" "-fno-rtti"
)
target_link_libraries(clang-highlight PRIVATE
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
    llvm::libs
)

if(DEFINED SKBUILD_PROJECT_NAME)
    # Hack to make importlib.resources work properly (the logic in
    # scikit-build-core for this expects a file in the package root).
    # Furthermore, our executable needs to be in a sub-module.
    file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/helper.txt" "")
    install(FILES "${CMAKE_CURRENT_BINARY_DIR}/helper.txt" DESTINATION ${SKBUILD_PROJECT_NAME})

    install(TARGETS clang-highlight DESTINATION ${SKBUILD_PROJECT_NAME}/_util)

    # Include clang's internal headers
    install(
        DIRECTORY "${LLVM_LIBRARY_DIR}/clang/${LLVM_VERSION_MAJOR}/include"
        DESTINATION "${SKBUILD_PROJECT_NAME}/lib/clang/${LLVM_VERSION_MAJOR}"
    )
endif()
