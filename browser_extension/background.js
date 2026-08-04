importScripts('compromise.js', 'classifier.js', 'service_worker.js');
// Eagerly load phrase config so classifySync is ready before any navigation.
// After loading, reflect any config error as a red badge on the extension icon.
void loadConfig().then(async () => {
  const err = await getConfigError();
  if (err) {
    chrome.action.setBadgeText({ text: 'ERR' });
    chrome.action.setBadgeBackgroundColor({ color: '#8b0000' });
    chrome.action.setTitle({ title: 'Purity — Config error: ' + err });
  } else {
    chrome.action.setBadgeText({ text: '' });
    chrome.action.setTitle({ title: 'Purity Intentional Browsing' });
  }
});

const SESSION_URL = "http://127.0.0.1:8765/browser-session";
const INTERNET_SETTINGS_URL = "http://127.0.0.1:8765/internet-settings";
const HEARTBEAT_URL = "http://127.0.0.1:8765/extension-heartbeat";
const POLL_MS = 3000;
const BLACKLIST_POLL_MS = 30000;
const BLOCK_RULE_ID = 1;
const LOCALHOST_ALLOW_RULE_ID = 2;
const HEARTBEAT_ALARM = "purity-extension-heartbeat";
const HEARTBEAT_PERIOD_MINUTES = 0.5;

let currentSession = { is_active: false };
let blacklistedDomains = [];
const blockedByTabId = new Map();
let ruleUpdateChain = Promise.resolve();

async function getInstanceId() {
  const stored = await chrome.storage.local.get("instanceId");
  if (stored?.instanceId) {
    return stored.instanceId;
  }
  const instanceId = self.crypto?.randomUUID ? self.crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  await chrome.storage.local.set({ instanceId });
  return instanceId;
}

async function sendHeartbeat() {
  try {
    const instanceId = await getInstanceId();
    await fetch(HEARTBEAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        extension_version: chrome.runtime.getManifest().version,
        instance_id: instanceId,
        source: "chrome_extension"
      })
    });
  } catch {
    return;
  }
}

function scheduleHeartbeatAlarm() {
  chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_PERIOD_MINUTES });
}

// priority 2 beats the block rule (priority 1); RE2 has no lookahead so a separate allow rule is required
function buildLocalhostAllowRule() {
  return {
    id: LOCALHOST_ALLOW_RULE_ID,
    priority: 2,
    action: { type: "allow" },
    condition: {
      regexFilter: "^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?(/|$)",
      resourceTypes: ["main_frame"]
    }
  };
}

function buildBlockRule() {
  return {
    id: BLOCK_RULE_ID,
    priority: 1,
    action: {
      type: "redirect",
      redirect: {
        // \0 is the entire matched URL; this embeds it in the fragment so
        // blocked.html can read it directly without a service-worker round-trip.
        regexSubstitution: chrome.runtime.getURL("blocked.html") + "#url=\\0"
      }
    },
    condition: {
      regexFilter: "^https?://.*",
      resourceTypes: ["main_frame"]
    }
  };
}

async function fetchSession() {
  try {
    const response = await fetch(SESSION_URL, { cache: "no-store" });
    if (!response.ok) {
      return { is_active: false };
    }
    return await response.json();
  } catch {
    return { is_active: false };
  }
}

async function fetchBlacklist() {
  try {
    const response = await fetch(INTERNET_SETTINGS_URL, { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    if (Array.isArray(data?.blacklisted_domains)) {
      blacklistedDomains = data.blacklisted_domains.map(d => String(d).toLowerCase());
    }
  } catch {
    // Server not reachable — keep existing cached list.
  }
}

function normalizeUrl(url) {
  try {
    return new URL(url).toString();
  } catch {
    return "";
  }
}

function buildRules(session) {
  // localhost is always reachable (dev servers, local tools) regardless of session state.
  const rules = [buildLocalhostAllowRule()];
  if (!session.is_active) {
    rules.push(buildBlockRule());
  }
  return rules;
}

async function replaceRules(rules) {
  const existingRules = await chrome.declarativeNetRequest.getDynamicRules();
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: existingRules.map((rule) => rule.id),
    addRules: rules
  });
}

async function syncRulesFromSession() {
  currentSession = await fetchSession();
  await replaceRules(buildRules(currentSession));
}

function updateFromSession() {
  ruleUpdateChain = ruleUpdateChain
    .catch(() => {})
    .then(() => syncRulesFromSession());
  return ruleUpdateChain;
}

function isBlacklistedHostname(hostname) {
  const host = (hostname || "").toLowerCase();
  return blacklistedDomains.some(
    (domain) => host === domain || host.endsWith("." + domain)
  );
}

function isGoogleImages(urlString) {
  try {
    const url = new URL(urlString);

    const isGoogle =
      url.hostname === "google.com" ||
      url.hostname === "www.google.com" ||
      url.hostname.endsWith(".google.com");

    if (!isGoogle) {
      return false;
    }

    const udm = url.searchParams.get("udm");
    const tbm = url.searchParams.get("tbm");

    return (
      udm === "2" ||
      tbm === "isch" ||
      url.pathname.startsWith("/imgres")
    );
  } catch {
    return false;
  }
}

/**
 * Extract the user-visible search query from a known search engine URL.
 * Returns null if the URL is not a recognised search engine results page.
 */
function extractSearchQuery(urlString) {
  try {
    const url = new URL(urlString);
    const host = url.hostname.replace(/^www\./, '');
    if (host === 'google.com' || host.endsWith('.google.com')) return url.searchParams.get('q');
    if (host === 'bing.com'   || host.endsWith('.bing.com'))   return url.searchParams.get('q');
    if (host === 'duckduckgo.com')                             return url.searchParams.get('q');
    if (host === 'search.yahoo.com')                           return url.searchParams.get('p');
    return null;
  } catch {
    return null;
  }
}

chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
  if (details.frameId !== 0) {
    return;
  }
  const extensionBase = chrome.runtime.getURL("");
  if (details.url.startsWith(extensionBase)) {
    return;
  }
  void sendHeartbeat();
  const searchQuery = extractSearchQuery(details.url);
  if (searchQuery) {
    await loadConfig(); // no-op if already loaded; ensures soft_risk phrases are available
    const result = classifySync(searchQuery);
    if (result.level === 'HARD_BLOCK') {
      chrome.tabs.update(details.tabId, {
        url: chrome.runtime.getURL("blocked.html")
          + "#reason=query&query=" + encodeURIComponent(searchQuery)
          + "&url=" + encodeURIComponent(details.url)
      });
      return;
    }
    if (result.level === 'SOFT_RISK') {
      chrome.tabs.update(details.tabId, {
        url: chrome.runtime.getURL("blocked.html")
          + "#reason=query-warn&query=" + encodeURIComponent(searchQuery)
          + "&url=" + encodeURIComponent(details.url)
      });
      return;
    }
  }
  if (isGoogleImages(details.url)) {
    const warningUrl =
      chrome.runtime.getURL("google_images_warning.html") +
      "#url=" + encodeURIComponent(details.url);
    chrome.tabs.update(details.tabId, { url: warningUrl });
    return;
  }
  // Blacklist check — applies whenever a session is active.
  if (currentSession.is_active && blacklistedDomains.length > 0) {
    try {
      const hostname = new URL(details.url).hostname;
      if (isBlacklistedHostname(hostname)) {
        chrome.tabs.update(details.tabId, {
          url: chrome.runtime.getURL("blocked.html")
            + "#reason=blacklisted&url=" + encodeURIComponent(details.url)
        });
        return;
      }
    } catch {
      // Invalid URL — let it pass through.
    }
  }
});

chrome.runtime.onInstalled.addListener(() => {
  scheduleHeartbeatAlarm();
  void sendHeartbeat();
  void fetchBlacklist();
  void updateFromSession();
});
chrome.runtime.onStartup.addListener(() => {
  scheduleHeartbeatAlarm();
  void sendHeartbeat();
  void fetchBlacklist();
  void updateFromSession();
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === HEARTBEAT_ALARM) {
    void sendHeartbeat();
  }
});
scheduleHeartbeatAlarm();
void sendHeartbeat();
void fetchBlacklist();
void updateFromSession();
setInterval(() => {
  void updateFromSession();
}, POLL_MS);
setInterval(() => {
  void fetchBlacklist();
}, BLACKLIST_POLL_MS);

async function logDetection({ level, score, matches, url }) {
  if (level === 'SAFE') return;
  try {
    const instanceId = await getInstanceId();
    await fetch('http://127.0.0.1:8765/browser-session/detection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, score, matches, url, timestamp: Date.now(), instance_id: instanceId })
    });
  } catch {
    return;
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "get-config-error") {
    getConfigError().then(err => sendResponse({ error: err || null }));
    return true;
  }

  if (message?.type === "classify") {
    handleClassifyMessage(message, (result) => {
      sendResponse(result);
      void logDetection(result);
    });
    return true;
  }

  if (message?.type === "classify_page_content") {
    handleClassifyPageContentMessage(message, (result) => {
      sendResponse(result);
    });
    return true;
  }

  if (message?.type === "get-blocked-url") {
    sendResponse({ url: blockedByTabId.get(sender.tab?.id) || "" });
    return;
  }
});