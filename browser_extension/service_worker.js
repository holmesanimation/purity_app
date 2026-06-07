// service_worker.js — Config loader + classifier wrapper + message handler.
// Loaded into background.js via importScripts('classifier.js', 'service_worker.js').
// classifier.js must be imported first so classify() is in scope.

// Minimal fallback used when monitored_phrases.json cannot be fetched.
const EMERGENCY_DEFAULTS = {
  hard_block: [
    { phrase: 'porn',        weight: 100 },
    { phrase: 'pornography', weight: 100 },
    { phrase: 'onlyfans',    weight: 100 }
  ],
  soft_risk: []
};

/** Cached phrase config. Null until first classification call. */
let phraseConfig = null;

/** Human-readable error from the last failed load attempt. Null when healthy. */
let configError = null;

/** Singleton promise — ensures config is only fetched once per SW lifetime. */
let _configPromise = null;

/**
 * Validate the structure of a parsed config object.
 * Returns a descriptive error string, or null if valid.
 * @param {*} config
 * @returns {string|null}
 */
function validateConfig(config) {
  if (!config || typeof config !== 'object') return 'Config is not an object.';
  if (!Array.isArray(config.hard_block)) return 'Missing or invalid "hard_block" array.';
  if (!Array.isArray(config.soft_risk))  return 'Missing or invalid "soft_risk" array.';
  for (const [list, name] of [[config.hard_block, 'hard_block'], [config.soft_risk, 'soft_risk']]) {
    for (let i = 0; i < list.length; i++) {
      const entry = list[i];
      if (typeof entry.phrase !== 'string' || entry.phrase.trim() === '') {
        return `${name}[${i}] is missing a valid "phrase" string.`;
      }
      if (typeof entry.weight !== 'number') {
        return `${name}[${i}] ("${entry.phrase}") is missing a numeric "weight".`;
      }
    }
  }
  return null;
}

/**
 * Persist or clear the config error in storage so it survives SW restarts.
 * @param {string|null} message
 */
async function setConfigError(message) {
  configError = message;
  await chrome.storage.local.set({ purityConfigError: message || null });
}

/** Returns the current config error, checking storage if the SW just restarted. */
async function getConfigError() {
  if (configError !== null) return configError;
  const stored = await chrome.storage.local.get('purityConfigError');
  configError = stored.purityConfigError || null;
  return configError;
}

/**
 * Fetch and cache monitored_phrases.json from the extension bundle.
 * Idempotent: subsequent calls return the same promise without re-fetching.
 * Falls back to EMERGENCY_DEFAULTS on any failure and stores the error.
 * @returns {Promise<void>}
 */
async function loadConfig() {
  if (_configPromise) return _configPromise;
  _configPromise = (async () => {
    let rawText = null;
    try {
      const url = chrome.runtime.getURL('config/monitored_phrases.json');
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch config: HTTP ${response.status}`);
      }
      rawText = await response.text();
    } catch (err) {
      const msg = `[PurityApp] Could not load monitored_phrases.json: ${err.message}`;
      console.error(msg);
      await setConfigError(msg);
      phraseConfig = EMERGENCY_DEFAULTS;
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(rawText);
    } catch (err) {
      const msg = `[PurityApp] monitored_phrases.json has a JSON syntax error: ${err.message}`;
      console.error(msg);
      await setConfigError(msg);
      phraseConfig = EMERGENCY_DEFAULTS;
      return;
    }
    const validationError = validateConfig(parsed);
    if (validationError) {
      const msg = `[PurityApp] monitored_phrases.json failed validation: ${validationError}`;
      console.error(msg);
      await setConfigError(msg);
      phraseConfig = EMERGENCY_DEFAULTS;
      return;
    }
    phraseConfig = {
      hard_block: expandPhrases(parsed.hard_block),
      soft_risk:  expandPhrases(parsed.soft_risk),
    };
    await setConfigError(null); // clear any previous error
    console.log('[PurityApp] Config loaded. Expanded phrase count:', phraseConfig.hard_block.length + phraseConfig.soft_risk.length);
  })();
  return _configPromise;
}

/**
 * Ensure config is loaded, then classify the given text.
 * @param {string} text
 * @returns {Promise<{level: string, score: number, matches: Array}>}
 *
 * // FUTURE: native messaging — replace classifyText() body with a call to
 * //   chrome.runtime.sendNativeMessage('com.purityapp.classifier', {text}, callback)
 * // FUTURE: AI moderation model — POST to a locally-running model server (Ollama, llama.cpp HTTP)
 */
async function classifyText(text) {
  if (!phraseConfig) {
    await loadConfig();
  }
  return classify(text, phraseConfig);
}

/**
 * Synchronous classification using cached config, or EMERGENCY_DEFAULTS if config
 * has not yet loaded. Safe to call from synchronous contexts (e.g. navigation handlers).
 * @param {string} text
 * @returns {{level: string, score: number, matches: Array}}
 */
function classifySync(text) {
  return classify(text, phraseConfig || EMERGENCY_DEFAULTS);
}

/**
 * Message handler called by background.js for { type: 'classify' } messages.
 * @param {{type: string, text: string, url: string}} request
 * @param {function} sendResponse
 * @returns {true}  Signals async response to Chrome.
 */
function handleClassifyMessage(request, sendResponse) {
  classifyText(request.text).then(result => {
    sendResponse({ level: result.level, score: result.score, matches: result.matches, url: request.url });
  });
  return true; // Keep the message channel open for async response.
}
