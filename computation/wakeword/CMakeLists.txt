cmake_minimum_required(VERSION 3.14)
project(wakeword_matcher CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Optimization flags ────────────────────────────────────────────────────────
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# ── Source files ──────────────────────────────────────────────────────────────
set(SOURCES
    wakeword_matcher.cpp
    weighted_levenshtein.cpp
    wakeword_similarity.cpp
)

# ── Binary ────────────────────────────────────────────────────────────────────
add_executable(wakeword_matcher ${SOURCES})

target_include_directories(wakeword_matcher PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# ── Install target (optional) ─────────────────────────────────────────────────
install(TARGETS wakeword_matcher DESTINATION bin)
