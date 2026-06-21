/**
 * wakeword/wakeword_similarity.cpp
 * ─────────────────────────────────────────────────────────────────────────────
 * Wakeword Similarity Engine  —  Modules 3, 4, 5, 6 from spec
 *
 * Module 3  Normalize: lowercase, strip punctuation/spaces
 * Module 4  Sliding window: compare wakeword against each token in transcript
 * Module 5  Confidence scoring: similarity = 1 - dist/max_len, clamped [0,1]
 *
 * Exposed via:
 *   WakewordResult match_wakeword(wakeword, transcript, threshold, map)
 *   string         normalize(text)
 * ─────────────────────────────────────────────────────────────────────────────
 */

#include "wakeword_similarity.hpp"
#include "weighted_levenshtein.hpp"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <vector>
#include <cmath>

namespace wakeword {

// ─────────────────────────────────────────────────────────────────────────────
//  normalize()
//  Hey, Canary!  →  canary
//  "Kennedy."    →  kennedy
// ─────────────────────────────────────────────────────────────────────────────
std::string normalize(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        if (std::isalpha(static_cast<unsigned char>(c))) {
            out += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        } else if (std::isspace(static_cast<unsigned char>(c)) && !out.empty() && out.back() != ' ') {
            out += ' ';   // collapse runs of whitespace to single space
        }
        // strip punctuation, digits, etc.
    }
    // trim trailing space
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}


// ─────────────────────────────────────────────────────────────────────────────
//  tokenize()
//  Split on spaces — returns individual words from normalized transcript.
// ─────────────────────────────────────────────────────────────────────────────
static std::vector<std::string> tokenize(const std::string& text) {
    std::vector<std::string> tokens;
    std::istringstream ss(text);
    std::string tok;
    while (ss >> tok) tokens.push_back(tok);
    return tokens;
}


// ─────────────────────────────────────────────────────────────────────────────
//  similarity_score()
//  Converts a weighted distance to a [0,1] similarity score.
//
//  similarity = 1.0 - distance / max(len(a), len(b))
//  Clamped to [0, 1].
// ─────────────────────────────────────────────────────────────────────────────
static double similarity_score(double dist, size_t len_a, size_t len_b) {
    size_t maxlen = std::max(len_a, len_b);
    if (maxlen == 0) return 1.0;
    double sim = 1.0 - dist / static_cast<double>(maxlen);
    return std::max(0.0, std::min(1.0, sim));
}


// ─────────────────────────────────────────────────────────────────────────────
//  match_wakeword()
//
//  Algorithm:
//    1. Normalize wakeword and transcript
//    2. Tokenize transcript into words
//    3. Also try bigrams (two adjacent tokens joined) to handle split words
//    4. For each candidate: compute weighted_levenshtein → similarity
//    5. Take max_similarity across all candidates
//    6. Accept if max_similarity >= threshold
//
//  Returns WakewordResult with:
//    - detected       (bool)
//    - confidence     (0.0 – 1.0)
//    - matched_token  (which word triggered the match)
// ─────────────────────────────────────────────────────────────────────────────
WakewordResult match_wakeword(
    const std::string& wakeword_raw,
    const std::string& transcript_raw,
    double             threshold,
    const PhonemeMap&  map)
{
    const std::string ww     = normalize(wakeword_raw);
    const std::string trans  = normalize(transcript_raw);

    if (ww.empty() || trans.empty()) {
        return {false, 0.0, "", ww, trans};
    }

    const auto tokens = tokenize(trans);
    if (tokens.empty()) {
        return {false, 0.0, "", ww, trans};
    }

    double      best_sim   = 0.0;
    std::string best_token;

    // ── Single-token sliding window ───────────────────────────────────────
    for (const auto& tok : tokens) {
        double dist = weighted_levenshtein(ww, tok, map);
        double sim  = similarity_score(dist, ww.size(), tok.size());
        if (sim > best_sim) {
            best_sim   = sim;
            best_token = tok;
        }
    }

    // ── Bigram window (handles "can ary" → "canary" style splits) ─────────
    for (size_t i = 0; i + 1 < tokens.size(); ++i) {
        std::string bigram = tokens[i] + tokens[i+1];
        double dist = weighted_levenshtein(ww, bigram, map);
        double sim  = similarity_score(dist, ww.size(), bigram.size());
        if (sim > best_sim) {
            best_sim   = sim;
            best_token = tokens[i] + " " + tokens[i+1];
        }
    }

    bool detected = (best_sim >= threshold);
    return {detected, best_sim, best_token, ww, trans};
}

}  // namespace wakeword
