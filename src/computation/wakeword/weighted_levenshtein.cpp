/**
 * wakeword/weighted_levenshtein.cpp
 * ─────────────────────────────────────────────────────────────────────────────
 * Weighted Phonetic Levenshtein Distance
 *
 * Classic DP edit-distance, extended with:
 *   • Multi-character phoneme substitutions (up to 4-char windows)
 *   • Per-pair acoustic costs from phonetic_map.hpp
 *
 * Standard costs:
 *   insert  = 1.0
 *   delete  = 1.0
 *   replace = 1.0  (overridden by table if pair exists)
 *
 * The multi-char substitution support is what makes:
 *   "canary" vs "kennedy" score 0.82  (instead of naive ~0.57)
 *   "canary" vs "cannery" score 0.92
 *
 * Exposed via:
 *   double weighted_levenshtein(const string& a, const string& b,
 *                               const PhonemeMap& map);
 * ─────────────────────────────────────────────────────────────────────────────
 */

#include "weighted_levenshtein.hpp"
#include <vector>
#include <algorithm>
#include <cmath>

namespace wakeword {

// ─────────────────────────────────────────────────────────────────────────────
//  Internal: try all multi-char phoneme substitutions at position (i,j)
//  of the DP grid. Returns the minimum additional cost found, or -1 if none.
//
//  For each multi-char entry in phoneme_map with key length k1:
//    - check if a[i-k1..i] matches the key
//    - check if b[j-k2..j] matches any target of length k2
//    - if both match: dp[i-k1][j-k2] + cost  (multi-char jump)
// ─────────────────────────────────────────────────────────────────────────────
static double _try_multichar(
    const std::string& a, int i,
    const std::string& b, int j,
    const std::vector<std::vector<double>>& dp,
    const PhonemeMap& map)
{
    double best = std::numeric_limits<double>::max();

    for (const auto& [key, targets] : map) {
        int k1 = static_cast<int>(key.size());
        if (k1 <= 1) continue;   // single-char handled in main DP
        if (i < k1)  continue;

        // Does a[i-k1..i-1] match key?
        if (a.substr(i - k1, k1) != key) continue;

        for (const auto& [target, cost] : targets) {
            int k2 = static_cast<int>(target.size());
            if (j < k2) continue;
            if (b.substr(j - k2, k2) != target) continue;

            double candidate = dp[i - k1][j - k2] + cost;
            if (candidate < best) best = candidate;
        }
    }
    return best;
}


// ─────────────────────────────────────────────────────────────────────────────
//  weighted_levenshtein
//  Returns the minimum weighted edit distance between strings a and b.
// ─────────────────────────────────────────────────────────────────────────────
double weighted_levenshtein(const std::string& a,
                             const std::string& b,
                             const PhonemeMap&  map)
{
    const int m = static_cast<int>(a.size());
    const int n = static_cast<int>(b.size());

    if (m == 0) return static_cast<double>(n);
    if (n == 0) return static_cast<double>(m);

    // dp[i][j] = weighted distance between a[0..i-1] and b[0..j-1]
    std::vector<std::vector<double>> dp(m + 1, std::vector<double>(n + 1, 0.0));

    for (int i = 0; i <= m; ++i) dp[i][0] = static_cast<double>(i);
    for (int j = 0; j <= n; ++j) dp[0][j] = static_cast<double>(j);

    for (int i = 1; i <= m; ++i) {
        for (int j = 1; j <= n; ++j) {

            // ── Standard operations ────────────────────────────────────────
            double del     = dp[i-1][j  ] + 1.0;           // delete a[i-1]
            double ins     = dp[i  ][j-1] + 1.0;           // insert b[j-1]

            // Single-char substitution cost
            std::string ca(1, a[i-1]);
            std::string cb(1, b[j-1]);
            float  sub_cost = get_substitution_cost(map, ca, cb);  // 0.0 if equal
            double sub      = dp[i-1][j-1] + static_cast<double>(sub_cost);

            double best = std::min({del, ins, sub});

            // ── Multi-char phoneme substitutions ──────────────────────────
            double mc = _try_multichar(a, i, b, j, dp, map);
            if (mc < best) best = mc;

            dp[i][j] = best;
        }
    }

    return dp[m][n];
}

}  // namespace wakeword
