cmake_minimum_required(VERSION 3.16)
project(eschess_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

set(CMAKE_CXX_FLAGS_RELEASE "-O2 -march=native -DNDEBUG")

# Core engine, shared by the UCI binary and the perft test.
add_library(eschess_core STATIC
    src/board.cpp
    src/zobrist.cpp
    src/evaluate.cpp
    src/tt.cpp
    src/search.cpp
)
target_include_directories(eschess_core PUBLIC src)

# The UCI binary: drives the engine over stdin/stdout (harness/match.py, GUI).
add_executable(uci src/uci.cpp)
target_link_libraries(uci PRIVATE eschess_core)

# Movegen validation against the Python engine's perft counts.
add_executable(perft test/perft.cpp)
target_link_libraries(perft PRIVATE eschess_core)
