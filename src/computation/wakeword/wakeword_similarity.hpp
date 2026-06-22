/**
 * wakeword/wakeword_similarity.hpp
 * ─────────────────────────────────────────────────────────────────────────────
 * Header for the wakeword similarity engine.
 * ─────────────────────────────────────────────────────────────────────────────
 */

#pragma once

#include "phonetic_map.hpp"
#include <string>

namespace wakeword {

/**
 * WakewordResult
 * Returned by match_wakeword().
 */
struct WakewordResult {
    bool        detected;       ///< true if max_similarity >= threshold
    double      confidence;     ///< best similarity score [0.0, 1.0]
    std::string matched_token;  ///< the transcript token that triggered the match
    std::string normalized_ww;  ///< normalized wakeword (for debugging)
    std::string normalized_tr;  ///< normalized transcript (for debugging)
};

/**
 * normalize()
 * Lowercase + strip punctuation.  "Hey, Canary!" → "hey canary"
 */
std::string normalize(const std::string& text);

/**
 * match_wakeword()
 * Runs the full pipeline:
 *   normalize → tokenize → sliding window → weighted DP → confidence score
 *
 * @param wakeword_raw  The target wake word (e.g. "canary")
 * @param transcript_raw Full ASR transcript (e.g. "hey kennedy can you play music")
 * @param threshold     Accept if confidence >= threshold (default 0.75)
 * @param map           Phoneme cost table from build_phoneme_map()
 */
WakewordResult match_wakeword(
    const std::string& wakeword_raw,
    const std::string& transcript_raw,
    double             threshold,
    const PhonemeMap&  map);

}  // namespace wakeword
