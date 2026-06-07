// classifier.js — Pure classification logic. No Chrome APIs.
// Loaded via importScripts() in the service worker. Also node-testable.

/**
 * Lowercase, trim, and collapse consecutive whitespace to a single space.
 * @param {string} text
 * @returns {string}
 */
function normalize(text) {
  return text.toLowerCase().trim().replace(/\s+/g, ' ');
}

/**
 * Split normalized text on spaces, take the last n words, and rejoin.
 * @param {string} text  Pre-normalized text.
 * @param {number} n     Number of trailing words to keep (default 8).
 * @returns {string}
 */
function extractRecentWords(text, n = 8) {
  const words = text.split(' ');
  return words.slice(-n).join(' ');
}

/**
 * Expand entries marked with `expand: true` into inflected verb forms using compromise.
 * Generates: base, 3rd-person singular, past tense, present participle.
 * Deduplicates by phrase so manual entries already covering a variant aren't doubled.
 * @param {Array<{phrase: string, weight: number, expand?: boolean}>} phraseList
 * @returns {Array<{phrase: string, weight: number}>}
 */
function expandPhrases(phraseList) {
  const expanded = [];
  const seen = new Set();
  for (const entry of phraseList) {
    if (!entry.expand) {
      if (!seen.has(entry.phrase)) {
        seen.add(entry.phrase);
        expanded.push({ phrase: entry.phrase, weight: entry.weight });
      }
      continue;
    }
    const verb = nlp(entry.phrase).verbs();
    const variants = [
      entry.phrase,
      verb.conjugate()[0]?.Infinitive   || entry.phrase,
      verb.conjugate()[0]?.PresentTense || (entry.phrase + 's'),
      verb.conjugate()[0]?.PastTense    || (entry.phrase + 'ed'),
      verb.conjugate()[0]?.Gerund       || (entry.phrase + 'ing'),
    ];
    for (const v of variants) {
      const norm = v.toLowerCase().trim();
      if (norm && !seen.has(norm)) {
        seen.add(norm);
        expanded.push({ phrase: norm, weight: entry.weight });
      }
    }
  }
  return expanded;
}

/**
 * Return every entry from phraseList whose phrase is a substring of normalizedText.
 * Multiple matches are returned — all matched phrases are included.
 * @param {string} normalizedText
 * @param {Array<{phrase: string, weight: number}>} phraseList
 * @returns {Array<{phrase: string, weight: number}>}
 *
 * // FUTURE: regex pattern support — add phraseEntry.regex field, test with RegExp(phraseEntry.regex)
 * // FUTURE: phrase groups — accumulate weight once per group, not per phrase
 */
function matchPhrases(normalizedText, phraseList) {
  return phraseList.filter(entry => normalizedText.includes(entry.phrase));
}

/**
 * Score text against hard_block and soft_risk phrase lists.
 * @param {string} text  Raw (un-normalized) text.
 * @param {{hard_block: Array, soft_risk: Array}} config
 * @returns {{score: number, hardMatches: Array, softMatches: Array}}
 */
function scoreText(text, config) {
  const normalized = normalize(text);
  const hardMatches = matchPhrases(normalized, config.hard_block);
  const softMatches = matchPhrases(normalized, config.soft_risk);
  const score = hardMatches.reduce((s, e) => s + e.weight, 0)
              + softMatches.reduce((s, e) => s + e.weight, 0);
  return { score, hardMatches, softMatches };
}

/**
 * Classify text as SAFE, SOFT_RISK, or HARD_BLOCK.
 * Both the full text and the trailing 8-word window are scored; the higher score wins.
 *
 * Thresholds: 0–29 = SAFE, 30–79 = SOFT_RISK, 80+ = HARD_BLOCK.
 *
 * @param {string} text
 * @param {{hard_block: Array, soft_risk: Array}} config
 * @returns {{level: 'SAFE'|'SOFT_RISK'|'HARD_BLOCK', score: number, matches: Array}}
 *
 * // FUTURE: category weighting — per-category threshold multipliers
 * // FUTURE: replace this function with a call to a Python native messaging classifier
 */
function classify(text, config) {
  const full   = scoreText(text, config);
  const recent = scoreText(extractRecentWords(normalize(text)), config);

  const best = full.score >= recent.score ? full : recent;
  const { score, hardMatches, softMatches } = best;
  const matches = [...hardMatches, ...softMatches];

  let level;
  if (score >= 80) {
    level = 'HARD_BLOCK';
  } else if (score >= 30) {
    level = 'SOFT_RISK';
  } else {
    level = 'SAFE';
  }

  return { level, score, matches };
}

// Allow use in Node.js (unit tests) without a browser environment.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { normalize, extractRecentWords, expandPhrases, matchPhrases, scoreText, classify };
}
