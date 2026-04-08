/****************************************************************
 *
 * @file preprocessor.cpp
 * @description Full preprocessor: tokenize → casefold → punct remove →
 *              stop word filter → Porter stem. Mirrors Python pipeline exactly.
 * @date April , 2026
 *
 ***************************************************************/

#include "preprocessor.hpp"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <unordered_set>

namespace {

/*==============================================================
 * Stop words
 * Must match Python STOP_WORDS frozenset exactly (normalizer.py).
 *==============================================================*/
static const std::unordered_set<std::string> STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
    "if", "in", "into", "is", "it", "no", "not", "of", "on", "or",
    "such", "that", "the", "their", "then", "there", "these", "they",
    "this", "to", "was", "will", "with", "about", "above", "after",
    "again", "all", "am", "any", "because", "been", "before", "being",
    "below", "between", "both", "can", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "from", "further",
    "get", "got", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "its",
    "itself", "just", "me", "might", "more", "most", "must", "my",
    "myself", "nor", "now", "off", "once", "only", "other", "our",
    "ours", "ourselves", "out", "over", "own", "re", "same", "she",
    "should", "so", "some", "still", "than", "them", "themselves",
    "those", "through", "too", "under", "until", "up", "very", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "would", "you", "your", "yours", "yourself", "yourselves",
};

class PorterStemmer {
    std::string b;  // word buffer — may be mutated by setto()
    int k;          // index of last valid character
    int k0;         // index of first character (always 0)
    int j;          // upper bound used by m(); set as side-effect of ends()

    /* Is b[i] a consonant? */
    bool cons(int i) {
        switch (b[i]) {
            case 'a': case 'e': case 'i': case 'o': case 'u':
                return false;
            case 'y':
                /* 'y' at word start → consonant; after consonant → vowel; after vowel → consonant */
                return (i == k0) ? true : !cons(i - 1);
            default:
                return true;
        }
    }

    /* Number of consonant-vowel (VC) sequences in b[k0..j]. */
    int m() {
        int n = 0, i = k0;
        /* skip initial C* */
        while (true) {
            if (i > j) return n;
            if (!cons(i)) break;
            ++i;
        }
        ++i;
        /* count VC sequences */
        while (true) {
            while (true) { if (i > j) return n; if ( cons(i)) break; ++i; } /* skip V* */
            ++i; ++n;
            while (true) { if (i > j) return n; if (!cons(i)) break; ++i; } /* skip C* */
            ++i;
        }
    }

    /* Does b[k0..j] contain at least one vowel? */
    bool vowelinstem() {
        for (int i = k0; i <= j; i++)
            if (!cons(i)) return true;
        return false;
    }

    /* Do positions jj and jj-1 form a double consonant? */
    bool doublec(int jj) {
        return jj >= k0 + 1 && b[jj] == b[jj - 1] && cons(jj);
    }

    /* Is the sequence at i-2, i-1, i a CVC pattern where b[i] ∉ {w, x, y}? */
    bool cvc(int i) {
        if (i < k0 + 2 || !cons(i) || cons(i - 1) || !cons(i - 2)) return false;
        const char c = b[i];
        return c != 'w' && c != 'x' && c != 'y';
    }

    /* Returns true iff b[k0..k] ends with s; sets j = k - len as side-effect. */
    bool ends(const char *s) {
        const int len = (int)std::strlen(s);
        if (b[k] != s[len - 1])                         return false;
        if (len > k - k0 + 1)                           return false;
        if (b.compare((size_t)(k - len + 1), (size_t)len, s) != 0) return false;
        j = k - len;
        return true;
    }

    /* Replace b[j+1..k] with s and update k. */
    void setto(const char *s) {
        const int len = (int)std::strlen(s);
        b.replace((size_t)(j + 1), (size_t)(k - j), s);
        k = j + len;
    }

    /* Apply setto(s) only when m() > 0. */
    void r(const char *s) { if (m() > 0) setto(s); }



    void step1ab() {
        /* Plural / past-tense removal */
        if (b[k] == 's') {
            if (ends("sses")) k -= 2;
            else if (ends("ies")) setto("i");
            else if (b[k - 1] != 's') k--;
        }
        if (ends("eed")) {
            if (m() > 0) k--;
        } else if ((ends("ed") || ends("ing")) && vowelinstem()) {
            k = j;
            if      (ends("at")) setto("ate");
            else if (ends("bl")) setto("ble");
            else if (ends("iz")) setto("ize");
            else if (doublec(k)) {
                const char c = b[k--];
                if (c == 'l' || c == 's' || c == 'z') k++;
            } else if (m() == 1 && cvc(k)) setto("e");
        }
    }

    void step1c() {
        /* (*v*) y → i */
        if (ends("y") && vowelinstem()) b[k] = 'i';
    }

    void step2() {
        if (k == k0) return;
        switch (b[k - 1]) {
            case 'a':
                if (ends("ational")) { r("ate");  break; }
                if (ends("tional")) { r("tion"); break; }
                break;
            case 'c':
                if (ends("enci")) { r("ence"); break; }
                if (ends("anci")) { r("ance"); break; }
                break;
            case 'e':
                if (ends("izer")) { r("ize");  break; }
                break;
            case 'l':
                if (ends("bli")){ r("ble");  break; }
                if (ends("alli")) { r("al");   break; }
                if (ends("entli")){ r("ent");  break; }
                if (ends("eli")) { r("e");    break; }
                if (ends("ousli")){ r("ous");  break; }
                break;
            case 'o':
                if (ends("ization")) { r("ize");  break; }
                if (ends("ation")){ r("ate");  break; }
                if (ends("ator")){ r("ate");  break; }
                break;
            case 's':
                if (ends("alism")) { r("al");   break; }
                if (ends("iveness")) { r("ive");  break; }
                if (ends("fulness")) { r("ful");  break; }
                if (ends("ousness")) { r("ous");  break; }
                break;
            case 't':
                if (ends("aliti")) { r("al");   break; }
                if (ends("iviti")){ r("ive");  break; }
                if (ends("biliti")) { r("ble");  break; }
                break;
            case 'g':
                /* NLTK extension */
                if (ends("logi")) { r("log");  break; }
                break;
        }
    }

    void step3() {
        switch (b[k]) {
            case 'e':
                if (ends("icate")) { r("ic");  break; }
                if (ends("ative")) { r("");    break; }
                if (ends("alize")) { r("al");  break; }
                break;
            case 'i':
                if (ends("iciti")) { r("ic");  break; }
                break;
            case 'l':
                if (ends("ical")){ r("ic");  break; }
                if (ends("ful")){ r("");    break; }
                break;
            case 's':
                if (ends("ness")){ r("");    break; }
                break;
        }
    }

    void step4() {
        if (k == k0) return;
        switch (b[k - 1]) {
            case 'a': if (ends("al"))    break; else return;
            case 'c':
                if (ends("ance"))        break;
                if (ends("ence"))        break;
                return;
            case 'e': if (ends("er"))    break; else return;
            case 'i': if (ends("ic"))    break; else return;
            case 'l':
                if (ends("able"))        break;
                if (ends("ible"))        break;
                return;
            case 'n':
                if (ends("ant"))         break;
                if (ends("ement"))       break;
                if (ends("ment"))        break;
                if (ends("ent"))         break;
                return;
            case 'o':
                if (ends("ion") && j >= k0 && (b[j] == 's' || b[j] == 't')) break;
                if (ends("ou"))          break;
                return;
            case 's': if (ends("ism"))   break; else return;
            case 't':
                if (ends("ate"))         break;
                if (ends("iti"))         break;
                return;
            case 'u': if (ends("ous"))   break; else return;
            case 'v': if (ends("ive"))   break; else return;
            case 'z': if (ends("ize"))   break; else return;
            default:  return;
        }
        if (m() > 1) k = j;
    }

    void step5ab() {
        /*
         * Step 5a: (m>1) e →  |  (m=1 and not *o) e →
         *
         * j is set to k-1 so that m() measures the stem WITHOUT
         * the trailing 'e'.  This matches NLTK's explicit stem[:-1]
         * approach and differs from the reference C code which relies
         * on a j left over from step4.
         */
        if (b[k] == 'e') {
            j = k - 1;
            const int a = m();
            if (a > 1 || (a == 1 && !cvc(k - 1))) k--;
        }
        /* Step 5b: (m>1 and *d and *L) → */
        j = k;
        if (b[k] == 'l' && doublec(k) && m() > 1) k--;
    }

public:
    std::string stem(const std::string &word) {
        b  = word;
        k  = (int)word.size() - 1;
        k0 = 0;
        /* Words of length 0 or 1 are returned unchanged */
        if (k <= 1) return b.substr(0, (size_t)(k + 1));
        step1ab();
        step1c();
        step2();
        step3();
        step4();
        step5ab();
        return b.substr((size_t)k0, (size_t)(k - k0 + 1));
    }
};

} // anonymous namespace

/*
 * Preprocessor::process
 *
 * Mirrors the Python build-time pipeline for query terms:
 *   Tokenizer  → re.findall(r"[a-zA-Z0-9]+", text)
 *   CaseFolder → str.lower()
 *   PunctRemover → re.sub(r"[^a-zA-Z0-9]", "", token)
 *   StopWordFilter → discard if token in STOP_WORDS
 *   Stemmer    → NLTK PorterStemmer
 *
 * Boolean operators (\and / \or / \not, or their uppercase equivalents
 * AND / OR / NOT) bypass normalisation and are emitted as canonical
 * \and / \or / \not tokens expected by IR_System::processQuery().
 */
std::vector<std::string> Preprocessor::process(const std::string &raw_query) {
    std::vector<std::string> result;
    PorterStemmer stemmer;

    const size_t qlen = raw_query.size();
    size_t pos = 0;

    while (pos < qlen) {
        /* Skip whitespace */
        while (pos < qlen && std::isspace((unsigned char)raw_query[pos])) ++pos;
        if (pos >= qlen) break;

        /* Extract one whitespace-delimited chunk */
        const size_t chunk_start = pos;
        while (pos < qlen && !std::isspace((unsigned char)raw_query[pos])) ++pos;
        const std::string chunk = raw_query.substr(chunk_start, pos - chunk_start);

        /* Lowercase copy for operator detection */
        std::string chunk_lc = chunk;
        std::transform(chunk_lc.begin(), chunk_lc.end(), chunk_lc.begin(),
                       [](unsigned char c) { return (char)std::tolower(c); });

        /* ── Boolean operators ──────────────────────────────────────────── */
        /* Recognise \and / AND (and lowercase and — though that is also a  */
        /* stop word, treating it as an operator is more useful at query     */
        /* time).  Emit the canonical backslash form expected by IR_System.  */
        if (chunk_lc == "\\and" || chunk_lc == "and") { result.push_back("\\and"); continue; }
        if (chunk_lc == "\\or"  || chunk_lc == "or")  { result.push_back("\\or");  continue; }
        if (chunk_lc == "\\not" || chunk_lc == "not") { result.push_back("\\not"); continue; }

        /* ── Regular query term ─────────────────────────────────────────── */
        /* Extract alphanumeric sub-tokens: mirrors re.findall(r"[a-zA-Z0-9]+") */
        size_t i = 0;
        const size_t clen = chunk.size();
        while (i < clen) {
            /* Skip non-alphanumeric characters */
            while (i < clen && !std::isalnum((unsigned char)chunk[i])) ++i;
            if (i >= clen) break;

            const size_t tok_start = i;
            while (i < clen && std::isalnum((unsigned char)chunk[i])) ++i;
            std::string tok = chunk.substr(tok_start, i - tok_start);

            /* Stage 1: CaseFold */
            std::transform(tok.begin(), tok.end(), tok.begin(),
                           [](unsigned char c) { return (char)std::tolower(c); });

            /* Stage 2: PunctuationRemover — strip non-alphanumeric, drop empty.
             * The tokeniser above already guarantees an alphanumeric token, but
             * we apply the stage explicitly to match the Python pipeline. */
            std::string cleaned;
            cleaned.reserve(tok.size());
            for (char c : tok)
                if (std::isalnum((unsigned char)c)) cleaned += c;
            if (cleaned.empty()) continue;

            /* Stage 3: StopWordFilter */
            if (STOP_WORDS.count(cleaned)) continue;

            /* Stage 4: Porter stem */
            const std::string stemmed = stemmer.stem(cleaned);
            if (!stemmed.empty()) result.push_back(stemmed);
        }
    }

    return result;
}
