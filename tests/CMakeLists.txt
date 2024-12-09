
add_test(
    NAME clang-highlight-tests
    COMMAND env "PATH=$<TARGET_FILE_DIR:clang-highlight>:$ENV{PATH}" python "${CMAKE_CURRENT_SOURCE_DIR}/tests.py"
)
