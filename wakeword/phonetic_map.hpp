/**
 * wakeword/phonetic_map.hpp
 * ─────────────────────────────────────────────────────────────────────────────
 * Weighted Phonetic Similarity Engine  —  Phoneme Cost Table  (v2)
 *
 * Research basis:
 *   • Soundex / Metaphone / Double Metaphone groupings (Bell Labs, 1918–2000)
 *   • IPA articulatory proximity matrix (place × manner × voicing)
 *   • ASR/Whisper confusion patterns (Whisper quasi-oronyms, PER analysis)
 *   • Non-native speaker L1 interference (Spanish b/v, Asian r/l,
 *     Arabic/Hindi th→d, German v/w, French nasals, etc.)
 *   • Speech impairment / dysarthria substitutions
 *   • Common English spelling → phoneme irregularities
 *
 * Cost semantics:
 *   0.0  = identical
 *   0.1  = minimal distinction (same articulation, only voicing differs)
 *   0.2  = close (same manner, adjacent place)
 *   0.3  = moderate (same broad class, different place or manner)
 *   0.4  = distant (cross-class but acoustically adjacent)
 *   1.0  = default (no relationship)
 *
 * All entries are symmetric — build_phoneme_map() adds both directions.
 * ─────────────────────────────────────────────────────────────────────────────
 */

#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <utility>

namespace wakeword {

using PhonemeMap = std::unordered_map<
    std::string,
    std::vector<std::pair<std::string, float>>
>;

struct PhonemeEntry {
    const char* from;
    const char* to;
    float       cost;
};

// ─────────────────────────────────────────────────────────────────────────────
//  PHONEME PAIR TABLE
//  Organized into research-backed categories
// ─────────────────────────────────────────────────────────────────────────────
static const PhonemeEntry PHONEME_PAIRS[] = {

    // ═════════════════════════════════════════════════════════════════════════
    //  CATEGORY 1: VOWELS
    //  IPA vowel chart proximity — all English vowels can shift in accent/noise
    //  Source: English vowel quadrilateral, acoustic formant proximity
    // ═════════════════════════════════════════════════════════════════════════

    // Short vowels — very easy to mishear in noise (Soundex groups all vowels)
    {"a",  "e",  0.2f},   // /æ/ ↔ /ɛ/   "bad"↔"bed", "canary"↔"cenery"
    {"a",  "o",  0.2f},   // /æ/ ↔ /ɒ/   "cat"↔"cot"
    {"a",  "u",  0.2f},   // /æ/ ↔ /ʌ/   "cap"↔"cup"
    {"a",  "i",  0.3f},   // /æ/ ↔ /ɪ/   "can"↔"kin"
    {"e",  "i",  0.2f},   // /ɛ/ ↔ /ɪ/   "bed"↔"bid", "ken"↔"kin"
    {"e",  "o",  0.3f},   // /ɛ/ ↔ /ɒ/
    {"e",  "u",  0.25f},  // /ɛ/ ↔ /ʌ/
    {"i",  "u",  0.2f},   // /ɪ/ ↔ /ʌ/
    {"i",  "o",  0.3f},
    {"o",  "u",  0.2f},   // /ɒ/ ↔ /ʌ/   "cot"↔"cut"

    // Long vowels & diphthongs
    {"a",  "ay", 0.1f},   // "face"→"fayse" (Australian)
    {"i",  "ai", 0.1f},   // spelling variant
    {"o",  "oa", 0.1f},   // "go"→"goa"
    {"u",  "oo", 0.1f},   // "blue"↔"bloo"
    {"ee", "i",  0.1f},   // /iː/ ↔ /ɪ/  "feet"↔"fit"
    {"oo", "u",  0.15f},  // /uː/ ↔ /ʌ/  "food"↔"fud"
    {"oo", "o",  0.2f},   // "book"↔"bok"

    // Y as vowel — very common in word-final position
    {"y",  "i",  0.1f},   // "canary"→"canari"
    {"y",  "e",  0.15f},  // "canary"→"canare"
    {"y",  "ee", 0.1f},   // "very"→"veree"
    {"ie", "y",  0.1f},   // "canarie"→"canary"
    {"ie", "i",  0.1f},   // "canarie"→"canari"

    // Schwa absorption (very common in unstressed syllables — ASR drops them)
    {"a",  "",   0.35f},  // "canary" → "cnary" (schwa deletion)
    {"e",  "",   0.35f},
    {"er", "r",  0.2f},   // schwa+r reduction: "butter"→"buttr"
    {"ar", "r",  0.2f},   // British "canary"→"canry"
    {"or", "r",  0.2f},

    // ═════════════════════════════════════════════════════════════════════════
    //  CATEGORY 2: PLOSIVES (Hard Consonants)
    //  Source: Soundex group 1 (BFPV), group 2 (CGJKQSXZ), group 3 (DT)
    //          Articulatory: voicing distinction only
    // ═════════════════════════════════════════════════════════════════════════

    // Voicing pairs (minimal articulatory difference)
    {"b",  "p",  0.1f},   // voiced↔voiceless bilabial plosive
    {"d",  "t",  0.1f},   // voiced↔voiceless alveolar plosive
    {"g",  "k",  0.1f},   // voiced↔voiceless velar plosive

    // Velar family — same place, different voicing/aspiration
    {"c",  "k",  0.05f},  // spelling variant of same sound
    {"k",  "q",  0.1f},   // "queen"↔"keen"
    {"c",  "q",  0.1f},
    {"ck", "k",  0.05f},  // "back"→"bak"
    {"qu", "kw", 0.1f},   // "queen"→"kween"
    {"c",  "s",  0.15f},  // soft-C: "city"→"sity"
    {"c",  "g",  0.15f},  // hard-C ↔ G: "cat"↔"gat" (accent)

    // ═════════════════════════════════════════════════════════════════════════
    //  CATEGORY 3: FRICATIVES & AFFRICATES (Soft Consonants)
    //  Source: IPA manner=fricative, Soundex group 1 (BFPV), group 2
    // ═════════════════════════════════════════════════════════════════════════

    // Labio-dental pair
    {"f",  "v",  0.1f},   // "fan"↔"van" — voicing only
    {"ph", "f",  0.05f},  // spelling: "phone"→"fone"
    {"ph", "v",  0.15f},

    // Labio-dental ↔ bilabial (very common non-native)
    {"v",  "b",  0.15f},  // Spanish: "vamos"→"bamos" — b/v allophony
    {"v",  "w",  0.15f},  // German/Hindi: "very"→"wery"
    {"w",  "b",  0.2f},   // some Asian languages

    // Alveolar fricative pair
    {"s",  "z",  0.1f},   // "see"↔"zee" — voicing only
    {"s",  "sh", 0.15f},  // "suit"→"shuit" (some accents)
    {"z",  "zh", 0.15f},  // "azure"↔"a-zh-ure"
    {"x",  "ks", 0.05f},  // "fox"→"foks" (spelling)
    {"x",  "gz", 0.1f},   // "example"→"egzample"
    {"x",  "z",  0.15f},  // "xylophone"→"zylophone"

    // Palatal / post-alveolar
    {"sh", "zh", 0.1f},   // "ship"↔"zhip" (French accent)
    {"ch", "sh", 0.15f},  // "church"→"shursh" (non-native)
    {"ch", "k",  0.15f},  // Greek ch: "chorus"→"korus"
    {"j",  "y",  0.15f},  // "yes"↔"jes" (Spanish)
    {"j",  "dj", 0.05f},  // spelling variant
    {"g",  "j",  0.15f},  // soft-G: "gym"→"jim"
    {"g",  "zh", 0.2f},   // French g: "genre"→"zhonre"

    // TH sounds — missing from most world languages
    {"th", "d",  0.15f},  // /ð/→/d/ "the"→"de" (Arabic/Indian/Caribbean)
    {"th", "t",  0.15f},  // /θ/→/t/ "think"→"tink" (many accents)
    {"th", "f",  0.2f},   // /θ/→/f/ "three"→"free" (Cockney)
    {"th", "s",  0.2f},   // /θ/→/s/ "think"→"sink" (Greek/Spanish)
    {"th", "z",  0.2f},   // /ð/→/z/ "this"→"zis" (German)
    {"th", "v",  0.25f},  // /ð/→/v/ "the"→"ve" (Scandinavian)

    // ═════════════════════════════════════════════════════════════════════════
    //  CATEGORY 4: LIQUIDS & NASALS
    //  Source: IPA manner=lateral/rhotic/nasal; L1 interference research
    // ═════════════════════════════════════════════════════════════════════════

    // R/L liquid confusion — most well-documented ASR error globally
    {"r",  "l",  0.25f},  // Japanese/Korean/Chinese: "rice"→"lice"
    {"r",  "w",  0.25f},  // "very"→"vewy" (childlike/speech impairment)
    {"l",  "n",  0.2f},   // Portuguese/Korean: "Seoul"→"Seon"
    {"l",  "r",  0.25f},  // (symmetric handled by build; explicit for clarity)

    // Nasal confusion — collapse in whisper/noise/impairment
    {"n",  "m",  0.2f},   // bilabial vs alveolar nasal; collapses in coda
    {"n",  "ng", 0.15f},  // "running"→"rung-ing" (NG insertion)
    {"m",  "ng", 0.2f},
    {"n",  "ny", 0.15f},  // Spanish ñ: "canary"→"canyary"

    // ═════════════════════════════════════════════════════════════════════════
    //  CATEGORY 5: SYLLABLE-INITIAL CONSONANT CLUSTERS / SILENT LETTERS
    //  Source: Double Metaphone rules, English orthography irregularities
    // ═════════════════════════════════════════════════════════════════════════

    {"kn", "n",  0.15f},  // "knight"→"night" (silent k)
    {"gn", "n",  0.15f},  // "gnat"→"nat"
    {"wr", "r",  0.15f},  // "write"→"rite"
    {"wh", "w",  0.1f},   // "what"→"wat"
    {"wh", "h",  0.15f},  // "white"→"hite" (Irish)
    {"ps", "s",  0.15f},  // "psychology"→"sychology"
    {"pn", "n",  0.15f},  // "pneumonia"→"neumonia"
    {"ae", "e",  0.1f},   // "aesthetic"→"esthetic"

    // ═════════════════════════════════════════════════════════════════════════
    //  CATEGORY 6: MULTI-CHARACTER MORPHEME / SUFFIX PATTERNS
    //  Critical for wake-word-length words (5-8 chars)
    //  Source: Observed Whisper mis-transcriptions + phoneme shift rules
    // ═════════════════════════════════════════════════════════════════════════

    // ─── Suffix: -ary / -ery / -ory ──────────────────────────────────────
    // This is THE critical set for "canary" detection
    {"ary", "ery",  0.2f},  // "canary"→"canery"     vowel shift
    {"ary", "eri",  0.2f},  // "canary"→"caneri"
    {"ary", "ari",  0.15f}, // "canary"→"canari"     y→i
    {"ary", "arie", 0.15f}, // "canary"→"canarie"    y→ie
    {"ary", "ory",  0.25f}, // "canary"→"canory"
    {"ary", "ori",  0.25f}, // "canary"→"canori"
    {"ary", "arey", 0.15f}, // "canary"→"canarey"
    {"ary", "arry", 0.2f},  // "canary"→"canarry"    double-r

    // ─── Prefix: can- / ken- / kan- / con- ───────────────────────────────
    // Drives "canary" ↔ "kennedy"-family detection
    {"can", "ken", 0.2f},   // a→e + c→k: "can"→"ken"  CRITICAL for kennedy
    {"can", "kan", 0.1f},   // c→k only
    {"can", "kon", 0.15f},  // a→o
    {"can", "con", 0.15f},  // c stays, a→o
    {"can", "gen", 0.25f},  // c→g + a→e
    {"can", "gan", 0.2f},   // c→g
    {"ca",  "ke",  0.2f},   // c→k, a→e  (shorter prefix)
    {"ca",  "ka",  0.1f},

    // ─── Middle: -na- / -ne- ─────────────────────────────────────────────
    {"na",  "ne",  0.15f},  // a→e: "canary"→"cenery" via na→ne
    {"na",  "ni",  0.2f},
    {"na",  "nne", 0.15f},  // double-n: "canary"→"cannery"
    {"na",  "nna", 0.1f},   // "canary"→"cannary"

    // ─── Common English suffix patterns ───────────────────────────────────
    {"er",  "ar",  0.15f},  // "butter"↔"battar" (Indian/British accent)
    {"er",  "or",  0.15f},  // "actor"↔"acter"
    {"er",  "a",   0.2f},   // British: "butter"→"butta"
    {"or",  "ar",  0.15f},
    {"an",  "en",  0.1f},   // "can"→"ken", "man"→"men"   IMPORTANT
    {"an",  "in",  0.15f},  // "can"→"kin"
    {"en",  "in",  0.1f},   // "ken"→"kin"
    {"on",  "un",  0.15f},
    {"tion","shun",0.15f},  // "nation"→"nashun"
    {"tion","sion",0.1f},   // "station"→"stasion"
    {"sion","zhun",0.15f},  // "vision"→"vizhun"
    {"ck",  "k",   0.05f},  // "back"→"bak"
    {"ck",  "c",   0.05f},
    {"ge",  "j",   0.1f},   // "age"→"aj"
    {"dge", "j",   0.1f},   // "judge"→"juj"
    {"tch", "ch",  0.1f},   // "catch"→"cach"
    {"kk",  "k",   0.05f},  // double-k reduction
    {"nn",  "n",   0.05f},  // "cannary"→"canary"  double-n reduction
    {"mm",  "m",   0.05f},
    {"tt",  "t",   0.05f},
    {"ll",  "l",   0.05f},
    {"rr",  "r",   0.05f},
    {"ss",  "s",   0.05f},

    // ─── Vowel digraph equivalences ────────────────────────────────────────
    {"ai",  "ay",  0.05f},  // "rain"↔"rayn"
    {"ei",  "ay",  0.1f},   // "vein"↔"vayn"
    {"ea",  "ee",  0.1f},   // "meat"↔"meet"
    {"ea",  "e",   0.1f},   // "bread"↔"bred"
    {"oa",  "o",   0.1f},   // "coat"↔"cot"
    {"ow",  "o",   0.1f},   // "know"↔"no"
    {"ow",  "aw",  0.1f},   // "cow"↔"caw"
    {"ou",  "ow",  0.05f},  // "out"↔"owt"
    {"ou",  "u",   0.15f},  // "should"↔"shud"
    {"ue",  "oo",  0.1f},   // "blue"↔"bloo"
    {"ui",  "oo",  0.1f},   // "fruit"↔"froot"

    // ─── Wake-word specific: -nary / -nnery / -nedy patterns ─────────────
    // Explicitly modelled for "canary" ↔ "kennedy" family
    {"nary", "nery",  0.2f},   // "canary"→"canery"      a→e
    {"nary", "nedy",  0.35f},  // "canary"→"kennedy"     a→e + r→d + y→y
    {"nary", "nary",  0.0f},   // identity
    {"nar",  "ned",   0.3f},   // "canar"→"kened"  (sub-path for kennedy)
    {"nar",  "ner",   0.15f},  // a→e: "canar"→"caner"

    // ─── Consonant cluster simplification (fast speech) ──────────────────
    {"str", "str", 0.0f},
    {"nd",  "n",   0.2f},   // "friend"→"frien" (final-cluster drop)
    {"nt",  "n",   0.2f},   // "print"→"prin"
    {"st",  "s",   0.2f},   // "first"→"firs"
    {"ld",  "l",   0.2f},   // "cold"→"col"

    // ─── H-dropping (Cockney, some non-native) ────────────────────────────
    {"h",   "",    0.3f},   // "hello"→"ello"

};

// ─────────────────────────────────────────────────────────────────────────────
//  build_phoneme_map()
// ─────────────────────────────────────────────────────────────────────────────
inline PhonemeMap build_phoneme_map() {
    PhonemeMap m;
    const int N = static_cast<int>(sizeof(PHONEME_PAIRS) / sizeof(PHONEME_PAIRS[0]));
    for (int i = 0; i < N; ++i) {
        const auto& e = PHONEME_PAIRS[i];
        std::string from(e.from);
        std::string to(e.to);
        m[from].push_back({to,   e.cost});
        if (!to.empty())                        // don't add "" → from
            m[to  ].push_back({from, e.cost});  // symmetric
    }
    return m;
}

// ─────────────────────────────────────────────────────────────────────────────
//  get_substitution_cost()
// ─────────────────────────────────────────────────────────────────────────────
inline float get_substitution_cost(const PhonemeMap& m,
                                   const std::string& from,
                                   const std::string& to) {
    if (from == to) return 0.0f;
    auto it = m.find(from);
    if (it == m.end()) return 1.0f;
    float best = 1.0f;
    for (const auto& [candidate, cost] : it->second) {
        if (candidate == to && cost < best)
            best = cost;
    }
    return best;
}

}  // namespace wakeword
