# Plan: Chrome Extension Text Monitoring

Add a text-monitoring pipeline to the existing Purity Intentional Browsing extension.
Detect potentially sexual or temptation-related text typed into any browser input field.
Classify locally, warn or block inline, and log detections to the Purity App backend.

## Decisions

- **Scope**: Browser input fields only (input, textarea, contenteditable). No global keylogger.
- **Privacy**: Everything local. No cloud APIs. No external transmission.
- **service_worker.js**: Loaded into `background.js` via `importScripts()` — NOT a second service worker (MV3 allows only one). The name matches the spec but the file is a module, not a registered worker.
- **background.js**: Preserved and extended. Not renamed.
- **SOFT_RISK**: Warn-only overlay. User can dismiss and continue.
- **HARD_BLOCK**: Prevents form submission / Enter search. Overlay shown with no "proceed" option.
- **Backend logging**: Detections POSTed to `localhost:8765/browser-session/detection` (fire-and-forget, silent failure). Python endpoint is out of scope for this plan — add as follow-up.
- **Config format**: JSON (`config/monitored_phrases.json`). Loaded via `chrome.runtime.getURL` + `fetch`. Falls back to hardcoded emergency defaults if load fails.
- **Thresholds**: 0–29 = SAFE, 30–79 = SOFT_RISK, 80+ = HARD_BLOCK. Sum of matched phrase weights.
- **Debounce**: 500 ms on input events before sending for classification.
- **Overlay isolation**: Scoped CSS with `purity-overlay-*` prefix. `position: fixed`, `z-index: 2147483647`. Inline critical styles to survive aggressive page resets.
- **Visual theme**: Matches existing extension UI — `--accent: #315c3c`, `--warn: #8b4513`.

## File Layout

```
browser_extension/
├── manifest.json                  ← UPDATE — add content_scripts, extend web_accessible_resources
├── background.js                  ← UPDATE — importScripts, classify message case, logDetection()
├── classifier.js                  ← NEW — pure classification logic, no Chrome APIs
├── service_worker.js              ← NEW — config loader + classifier wrapper + message handler
├── overlay.js                     ← NEW — overlay UI injected into pages
├── content.js                     ← NEW — input monitoring, debounce, form interception
└── config/
    └── monitored_phrases.json     ← NEW — phrase lists with weights
```

Existing files (`blocked.html`, `blocked.js`, `google_images_warning.html`,
`google_images_warning.js`) are untouched.

## Phase 1 — Classifier Core (no Chrome APIs)

These three files form the "brain" — independently testable without a browser.

### `config/monitored_phrases.json`

Two top-level arrays: `hard_block` and `soft_risk`. Each entry: `{phrase, weight}`.

```json
{
  "hard_block": [
    {"phrase": "porn",        "weight": 100},
    {"phrase": "pornography", "weight": 100},
    {"phrase": "onlyfans",    "weight": 100},
    {"phrase": "nude",        "weight": 80},
    {"phrase": "naked",       "weight": 80},
    {"phrase": "nsfw",        "weight": 100},
    {"phrase": "hentai",      "weight": 100},
    {"phrase": "xxx",         "weight": 100},
    {"phrase": "sex video",   "weight": 100},
    {"phrase": "escort",      "weight": 90},
    {"phrase": "stripper",    "weight": 90}
  ],
  "soft_risk": [
    {"phrase": "lonely",        "weight": 20},
    {"phrase": "tempted",       "weight": 30},
    {"phrase": "home alone",    "weight": 30},
    {"phrase": "bored alone",   "weight": 30},
    {"phrase": "hook up",       "weight": 50},
    {"phrase": "hookup",        "weight": 50},
    {"phrase": "hot girls",     "weight": 60},
    {"phrase": "dating app",    "weight": 25},
    {"phrase": "instagram model","weight": 40},
    {"phrase": "bikini",        "weight": 35},
    {"phrase": "suggestive",    "weight": 25}
  ]
}
```

Future extension points (add to JSON, no classifier code changes):
- Add new categories as additional top-level arrays + `threshold` config block.
- Add `regex` field alongside `phrase` for pattern-based matching.
- Add `group` field for phrase family grouping.

### `classifier.js`

Pure functions. No `chrome.*` calls. Loaded via `importScripts` — runs in SW context, also
node-testable for unit tests.

```
normalize(text)
  → lowercase, trim, collapse consecutive whitespace to single space

extractRecentWords(text, n = 8)
  → split normalized text on spaces, take last n, rejoin

matchPhrases(normalizedText, phraseList)
  → [{phrase, weight}] for every entry whose phrase is a substring of normalizedText
  → allows multiple matches (all matched phrases are returned)

scoreText(text, config)
  → runs matchPhrases against hard_block and soft_risk lists
  → returns {score, hardMatches, softMatches}
  → score = sum of all matched weights (hard + soft combined)

classify(text, config)
  → calls scoreText
  → returns {level, score, matches}
  → level: 'SAFE' | 'SOFT_RISK' | 'HARD_BLOCK'
  → both full text and extractRecentWords(text) are scored; result = max(score(full), score(recent))
```

Extension point comments in code:
```js
// FUTURE: regex pattern support — add phraseEntry.regex field, test with RegExp(phraseEntry.regex)
// FUTURE: phrase groups — accumulate weight once per group, not per phrase
// FUTURE: category weighting — per-category threshold multipliers
// FUTURE: replace this function with a call to a Python native messaging classifier
```

### `service_worker.js`

Classification module. Loaded into `background.js` via `importScripts('classifier.js', 'service_worker.js')`.

```
phraseConfig  ← null until first classification call
EMERGENCY_DEFAULTS  ← minimal hardcoded hard_block list as fallback

loadConfig()
  → fetch(chrome.runtime.getURL('config/monitored_phrases.json'))
  → parse JSON, cache in phraseConfig
  → on failure: log warning, set phraseConfig = EMERGENCY_DEFAULTS

classifyText(text)
  → async — ensures config loaded, calls classify(text, phraseConfig)
  → returns {level, score, matches}

handleClassifyMessage(request, sendResponse)
  → called by background.js message router
  → calls classifyText(request.text), then sendResponse({level, score, matches, url: request.url})
  → returns true (async response)
```

Extension point comment:
```js
// FUTURE: native messaging — replace classifyText() body with a call to
//   chrome.runtime.sendNativeMessage('com.purityapp.classifier', {text}, callback)
// FUTURE: AI moderation model — POST to a locally-running model server (Ollama, llama.cpp HTTP)
```

## Phase 2 — Chrome Integration

### `overlay.js`

Content script. Loaded first (before content.js) so its globals are available.
Injects no DOM on load — only on demand.

```
window.PurityApp = {}

CSS: injected <style> tag once on first call, scoped with purity-overlay-* class names.
  - position: fixed, top: 0, left: 0, right: 0, z-index: 2147483647
  - Soft-risk: brown warning card (#8b4513 theme, matches google_images_warning.html)
  - Hard-block: red warning card (#8b0000)
  - Includes a Phil 4:8 scripture quote: "Whatever is true, whatever is honorable..."
  - Dismiss button for soft-risk; no proceed option on hard-block

PurityApp.showSoftRisk(matchedText, onDismiss)
  → renders warning overlay with matched context
  → dismiss button calls onDismiss() and removeOverlay()

PurityApp.showHardBlock(matchedText)
  → renders block overlay
  → calls PurityApp.onHardBlock(matchedText) if set
  → no "proceed" button

PurityApp.removeOverlay()
  → removes injected overlay element from DOM

PurityApp.onHardBlock = null
  // FUTURE: assign this in a future Purity panic workflow hook
  // e.g. PurityApp.onHardBlock = (text) => chrome.runtime.sendMessage({type: 'trigger-panic', text})
```

### `content.js`

Attached input listener and form interceptor. Depends on `overlay.js` globals.

```
DEBOUNCE_MS = 500

observeInputs()
  → scans document for input, textarea, [contenteditable] on load
  → MutationObserver watches for dynamically added elements
  → calls attachListener(el) for each

attachListener(el)
  → guards against double-attach with el.dataset.purityAttached = '1'
  → debounced 'input' event: calls sendForClassification(extractText(el))
  → calls interceptSubmission(el)

extractText(el)
  → reads el.value (input/textarea) or el.textContent (contenteditable)
  → returns full text (classifier does its own recent-word extraction)

interceptSubmission(el)
  → walks up DOM to find parent <form>, attaches 'submit' listener once (guarded)
  → for [role="searchbox"] and [type="search"]: attaches 'keydown' listener, catches Enter key
  → stores pending event reference so it can be cancelled after async classification

sendForClassification(text, pendingEvent)
  → skips if text is blank or < 3 chars
  → chrome.runtime.sendMessage({type: 'classify', text, url: location.href}, response => {
      if response.level === 'SAFE': no-op
      if response.level === 'SOFT_RISK': PurityApp.showSoftRisk(text, () => {})
      if response.level === 'HARD_BLOCK':
        if pendingEvent: pendingEvent.preventDefault(); pendingEvent.stopImmediatePropagation()
        PurityApp.showHardBlock(text)
        // FUTURE: PurityApp.onHardBlock hook called inside showHardBlock
    })
```

### `background.js` changes

Two additions only — existing session/blocking logic is untouched:

**Top of file:**
```js
importScripts('classifier.js', 'service_worker.js');
```

**In existing `chrome.runtime.onMessage` listener** — add case:
```js
case 'classify':
  handleClassifyMessage(request, sendResponse);
  logDetection(request, sendResponse);  // fire-and-forget after response
  return true;  // async response
```

**New function `logDetection(data)`:**
```js
async function logDetection({ level, score, matches, url }) {
  if (level === 'SAFE') return;
  try {
    const instanceId = await getInstanceId();  // reuse existing helper
    await fetch('http://127.0.0.1:8765/browser-session/detection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, score, matches, url, timestamp: Date.now(), instance_id: instanceId })
    });
  } catch {
    return;  // backend may not be running; fail silently
  }
}
```

### `manifest.json` changes

**Add `content_scripts` array** (alongside existing `background` key):
```json
"content_scripts": [
  {
    "matches": ["<all_urls>"],
    "js": ["overlay.js", "content.js"],
    "run_at": "document_idle"
  }
]
```

**Extend `web_accessible_resources[0].resources`** to include the config file:
```json
"config/monitored_phrases.json"
```

## Architecture Diagram

```
Page (tab)
  └── content.js  ──input event (debounced 500ms)──►  background.js
  └── overlay.js                                           │
         ▲                                          importScripts:
         │                                           classifier.js
         │  ◄── classification result ───────────  service_worker.js
         │                                                 │
  showSoftRisk / showHardBlock                      config/monitored_phrases.json
                                                          │
                                                    logDetection()
                                                          │
                                               POST localhost:8765/browser-session/detection
```

## Verification

1. Load unpacked extension from `browser_extension/` in `chrome://extensions` — confirm no manifest errors.
2. Open Extensions SW DevTools console — verify `importScripts` loads, `classifier.js` and `service_worker.js` globals visible.
3. Navigate to `google.com`, type `porn` in the search bar → HARD_BLOCK overlay appears, Enter key is swallowed.
4. Clear and type `lonely` → dismissible SOFT_RISK warning appears; after dismiss, typing continues normally.
5. Type `weather forecast` → no overlay.
6. DevTools → Network tab → confirm zero external requests (only `127.0.0.1`).
7. Check backend logs for `POST /browser-session/detection` on detections.
8. Delete `config/monitored_phrases.json` temporarily → confirm emergency fallback activates (SW console warning logged, `porn` still blocked).

## Follow-up: Python Backend Endpoint

`logDetection()` POSTs to `/browser-session/detection`. This endpoint does not yet exist.
Add to `services/browser_session_api_server.py`:
- Accept POST, parse JSON, validate `level` / `score` / `matches` / `url` / `timestamp`.
- Write detection event to journal/log using the active `run_id`.
- Return `{"ok": true}`.
Extension works without it (silent failure), so this can be deferred.
