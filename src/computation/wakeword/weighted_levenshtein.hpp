/**
 * wakeword/weighted_levenshtein.hpp
 * ─────────────────────────────────────────────────────────────────────────────
 * Header for the weighted Levenshtein DP engine.
 * ─────────────────────────────────────────────────────────────────────────────
 */

#pragma once

#include "phonetic_map.hpp"
#include <string>
#include <limits>

namespace wakeword {

/**
 * weighted_levenshtein
 *
 * Returns the minimum weighted edit distance between strings `a` and `b`.
 * Uses the phoneme cost table from `map` for substitution costs.
 * Multi-character phoneme mappings (e.g. "ary"→"ery") are also tried at
 * each DP cell to capture morpheme-level deformations.
 *
 * Standard costs: insert=1.0, delete=1.0, replace=1.0 (unless overridden).
 */
double weighted_levenshtein(const std::string& a,
                             const std::string& b,
                             const PhonemeMap&  map);

}  // namespace wakeword
