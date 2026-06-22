/**
 * wakeword/wakeword_matcher.cpp
 * ─────────────────────────────────────────────────────────────────────────────
 * Wakeword Matcher  —  CLI binary
 *
 * Usage:
 *   ./wakeword_matcher <wakeword> <transcript>
 *       → prints JSON result: {detected, confidence, matched_token}
 *
 *   ./wakeword_matcher --build-table <wakeword> [--threshold 0.75]
 *       → generates wakeword_config.json with lookup table of phonetic variants
 *         pre-computed by the DP engine for fast Python dict lookup
 *
 *   ./wakeword_matcher --benchmark <wakeword>
 *       → runs built-in acceptance/rejection benchmark and prints results
 *
 * Exit codes:
 *   0   wakeword detected / table built / benchmark passed
 *   1   wakeword NOT detected
 *   2   argument error
 * ─────────────────────────────────────────────────────────────────────────────
 */

#include "phonetic_map.hpp"
#include "weighted_levenshtein.hpp"
#include "wakeword_similarity.hpp"

#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <vector>
#include <string>
#include <algorithm>
#include <cstdlib>
#include <cstring>

// ─────────────────────────────────────────────────────────────────────────────
//  Minimal JSON helpers (no external dependency)
// ─────────────────────────────────────────────────────────────────────────────
static std::string json_escape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '"')  out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c == '\n') out += "\\n";
        else out += c;
    }
    return out;
}

static std::string dbl2str(double v, int prec = 4) {
    std::ostringstream ss;
    ss.precision(prec);
    ss << std::fixed << v;
    return ss.str();
}


// ─────────────────────────────────────────────────────────────────────────────
//  Phoneme variant generator
//  For --build-table: systematically generate candidate strings by applying
//  all single-step and two-step phoneme substitutions to `wakeword`.
//  Returns {candidate → best_similarity} for candidates with sim >= min_sim.
// ─────────────────────────────────────────────────────────────────────────────
static std::vector<std::pair<std::string,double>> generate_variants(
    const std::string& ww,
    const wakeword::PhonemeMap& map,
    double min_sim = 0.50)
{
    std::vector<std::pair<std::string,double>> results;

    // Helper: apply a substitution at position i (length `from_len`) → `to`
    auto apply_sub = [&](const std::string& base,
                         int i, int from_len,
                         const std::string& to) -> std::string {
        if (i < 0 || i + from_len > (int)base.size()) return "";
        return base.substr(0, i) + to + base.substr(i + from_len);
    };

    // All single-step variants
    std::vector<std::string> one_step;
    one_step.push_back(ww);   // include original

    for (const auto& [from, targets] : map) {
        int flen = static_cast<int>(from.size());
        // Find all occurrences of `from` in ww
        for (int i = 0; i <= (int)ww.size() - flen; ++i) {
            if (ww.substr(i, flen) == from) {
                for (const auto& [to, cost] : targets) {
                    std::string cand = apply_sub(ww, i, flen, to);
                    if (!cand.empty() && cand != ww)
                        one_step.push_back(cand);
                }
            }
        }
    }

    // Two-step variants (one_step variants with one more substitution)
    std::vector<std::string> two_step;
    for (const auto& base : one_step) {
        for (const auto& [from, targets] : map) {
            int flen = static_cast<int>(from.size());
            for (int i = 0; i <= (int)base.size() - flen; ++i) {
                if (base.substr(i, flen) == from) {
                    for (const auto& [to, cost] : targets) {
                        std::string cand = apply_sub(base, i, flen, to);
                        if (!cand.empty() && cand != ww && cand != base)
                            two_step.push_back(cand);
                    }
                }
            }
        }
    }

    // Merge all candidates, deduplicate
    std::vector<std::string> all_cands;
    all_cands.insert(all_cands.end(), one_step.begin(), one_step.end());
    all_cands.insert(all_cands.end(), two_step.begin(), two_step.end());
    std::sort(all_cands.begin(), all_cands.end());
    all_cands.erase(std::unique(all_cands.begin(), all_cands.end()), all_cands.end());

    // Score each candidate
    for (const auto& cand : all_cands) {
        if (cand == ww) {
            // original word itself gets perfect confidence in lookup table
            results.push_back({cand, 1.0});
            continue;
        }
        double dist = wakeword::weighted_levenshtein(ww, cand, map);
        double sim  = 1.0 - dist / std::max(ww.size(), cand.size());
        sim = std::max(0.0, std::min(1.0, sim));
        if (sim >= min_sim) {
            results.push_back({cand, sim});
        }
    }

    // Sort by confidence descending
    std::sort(results.begin(), results.end(),
              [](const auto& a, const auto& b){ return a.second > b.second; });

    return results;
}


// ─────────────────────────────────────────────────────────────────────────────
//  --build-table  mode
//  Writes wakeword_config.json to the same directory as the binary.
// ─────────────────────────────────────────────────────────────────────────────
static int cmd_build_table(const std::string& ww_raw,
                            double threshold,
                            const std::string& output_path)
{
    wakeword::PhonemeMap map = wakeword::build_phoneme_map();
    std::string ww = wakeword::normalize(ww_raw);

    if (ww.empty()) {
        std::cerr << "Error: empty wakeword after normalisation\n";
        return 2;
    }

    auto variants = generate_variants(ww, map, 0.50);

    // ── Build JSON ────────────────────────────────────────────────────────
    std::ostringstream js;
    js << "{\n";
    js << "  \"word\": \"" << json_escape(ww) << "\",\n";
    js << "  \"threshold\": " << dbl2str(threshold, 2) << ",\n";
    js << "  \"lookup_table\": {\n";

    bool first = true;
    for (const auto& [variant, conf] : variants) {
        if (!first) js << ",\n";
        js << "    \"" << json_escape(variant) << "\": " << dbl2str(conf, 4);
        first = false;
    }
    js << "\n  }\n}\n";

    // ── Write to file ─────────────────────────────────────────────────────
    std::ofstream f(output_path);
    if (!f.is_open()) {
        std::cerr << "Error: cannot write to " << output_path << "\n";
        return 2;
    }
    f << js.str();
    f.close();

    std::cout << "{\n";
    std::cout << "  \"status\": \"ok\",\n";
    std::cout << "  \"word\": \"" << json_escape(ww) << "\",\n";
    std::cout << "  \"threshold\": " << dbl2str(threshold, 2) << ",\n";
    std::cout << "  \"variants_generated\": " << variants.size() << ",\n";
    std::cout << "  \"output\": \"" << json_escape(output_path) << "\"\n";
    std::cout << "}\n";

    return 0;
}


// ─────────────────────────────────────────────────────────────────────────────
//  --benchmark  mode
// ─────────────────────────────────────────────────────────────────────────────
struct BenchCase {
    const char* input;
    bool        expect_accept;
};

static int cmd_benchmark(const std::string& ww_raw, double threshold) {
    wakeword::PhonemeMap map = wakeword::build_phoneme_map();

    // Dynamic: always test against the provided wakeword
    // Fixed test cases cover the spec's expected results
    std::vector<BenchCase> cases;

    // Accept cases: close phonetic variants of the wakeword
    if (ww_raw == "canary" || ww_raw == "Canary") {
        cases = {
            {"canary",   true},
            {"cannery",  true},
            {"canarie",  true},
            {"cannary",  true},
            {"kenary",   true},
            {"kennedy",  true},
            {"canery",   true},
            {"canari",   true},
            {"cannery",  true},
            {"kanary",   true},
            // Reject cases
            {"table",    false},
            {"banana",   false},
            {"weather",  false},
            {"spotify",  false},
            {"hello",    false},
            {"music",    false},
        };
    } else {
        // Generic: just test the word itself (accept) and common non-words (reject)
        cases.push_back({ww_raw.c_str(), true});
        cases.push_back({"table",        false});
        cases.push_back({"banana",       false});
        cases.push_back({"weather",      false});
        cases.push_back({"spotify",      false});
    }

    std::string ww = wakeword::normalize(ww_raw);
    int passed = 0, failed = 0;

    std::cout << "\nBenchmark: wakeword=\"" << ww << "\"  threshold=" << threshold << "\n";
    std::cout << std::string(60, '-') << "\n";
    std::cout << std::left;

    for (const auto& c : cases) {
        std::string input = c.input;
        auto res = wakeword::match_wakeword(ww, input, threshold, map);
        bool ok = (res.detected == c.expect_accept);

        std::string status     = ok    ? "✓ PASS" : "✗ FAIL";
        std::string expected   = c.expect_accept ? "ACCEPT" : "REJECT";
        std::string got        = res.detected    ? "ACCEPT" : "REJECT";

        std::cout << "  " << status << "  "
                  << std::setw(14) << input
                  << "  sim=" << dbl2str(res.confidence, 3)
                  << "  expected=" << expected
                  << "  got=" << got
                  << "\n";

        if (ok) ++passed; else ++failed;
    }

    std::cout << std::string(60, '-') << "\n";
    std::cout << "  Passed: " << passed << " / " << (passed + failed) << "\n\n";

    return (failed == 0) ? 0 : 1;
}


// ─────────────────────────────────────────────────────────────────────────────
//  match  mode  (default)
// ─────────────────────────────────────────────────────────────────────────────
static int cmd_match(const std::string& ww_raw,
                     const std::string& transcript,
                     double             threshold)
{
    wakeword::PhonemeMap map = wakeword::build_phoneme_map();
    auto res = wakeword::match_wakeword(ww_raw, transcript, threshold, map);

    std::cout << "{\n";
    std::cout << "  \"detected\": " << (res.detected ? "true" : "false") << ",\n";
    std::cout << "  \"confidence\": " << dbl2str(res.confidence, 4) << ",\n";
    std::cout << "  \"matched_token\": \"" << json_escape(res.matched_token) << "\",\n";
    std::cout << "  \"wakeword\": \"" << json_escape(res.normalized_ww) << "\",\n";
    std::cout << "  \"threshold\": " << dbl2str(threshold, 2) << "\n";
    std::cout << "}\n";

    return res.detected ? 0 : 1;
}


// ─────────────────────────────────────────────────────────────────────────────
//  main
// ─────────────────────────────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage:\n"
                  << "  wakeword_matcher <wakeword> <transcript>\n"
                  << "  wakeword_matcher --build-table <wakeword> [--threshold 0.75] [--output path/to/wakeword_config.json]\n"
                  << "  wakeword_matcher --benchmark <wakeword> [--threshold 0.75]\n";
        return 2;
    }

    std::string mode = argv[1];

    // ── --build-table ─────────────────────────────────────────────────────
    if (mode == "--build-table") {
        if (argc < 3) {
            std::cerr << "Error: --build-table requires a wakeword argument\n";
            return 2;
        }
        std::string ww        = argv[2];
        double      threshold = 0.75;
        std::string output    = "wakeword_config.json";

        for (int i = 3; i < argc - 1; ++i) {
            if (strcmp(argv[i], "--threshold") == 0)
                threshold = std::stod(argv[i+1]);
            if (strcmp(argv[i], "--output") == 0)
                output = argv[i+1];
        }
        return cmd_build_table(ww, threshold, output);
    }

    // ── --benchmark ───────────────────────────────────────────────────────
    if (mode == "--benchmark") {
        if (argc < 3) {
            std::cerr << "Error: --benchmark requires a wakeword argument\n";
            return 2;
        }
        std::string ww        = argv[2];
        double      threshold = 0.75;
        for (int i = 3; i < argc - 1; ++i) {
            if (strcmp(argv[i], "--threshold") == 0)
                threshold = std::stod(argv[i+1]);
        }
        return cmd_benchmark(ww, threshold);
    }

    // ── match mode: wakeword transcript ──────────────────────────────────
    if (argc < 3) {
        std::cerr << "Error: match mode requires <wakeword> <transcript>\n";
        return 2;
    }
    std::string ww         = argv[1];
    std::string transcript = argv[2];
    double      threshold  = 0.75;
    for (int i = 3; i < argc - 1; ++i) {
        if (strcmp(argv[i], "--threshold") == 0)
            threshold = std::stod(argv[i+1]);
    }
    return cmd_match(ww, transcript, threshold);
}
