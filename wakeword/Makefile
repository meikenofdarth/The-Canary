# wakeword/Makefile
# ─────────────────────────────────────────────────────────────────────────────
# Simple Makefile — alternative to CMake for systems without cmake installed.
#
# Usage:
#   cd wakeword && make          → builds ./build/wakeword_matcher
#   cd wakeword && make clean    → removes build artifacts
# ─────────────────────────────────────────────────────────────────────────────

CXX      ?= g++
CXXFLAGS  = -std=c++17 -O3 -DNDEBUG -Wall -Wextra -I.
BUILD_DIR = build
TARGET    = $(BUILD_DIR)/wakeword_matcher

SRCS = wakeword_matcher.cpp \
       weighted_levenshtein.cpp \
       wakeword_similarity.cpp

OBJS = $(patsubst %.cpp,$(BUILD_DIR)/%.o,$(SRCS))

.PHONY: all clean

all: $(BUILD_DIR) $(TARGET)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: %.cpp phonetic_map.hpp weighted_levenshtein.hpp wakeword_similarity.hpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $^ -o $@
	@echo ""
	@echo "  ✓  Built: $(TARGET)"
	@echo "  Run: ./$(TARGET) --benchmark canary"
	@echo ""

clean:
	rm -rf $(BUILD_DIR)
