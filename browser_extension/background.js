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
const ALLOW_URL = "http://127.0.0.1:8765/browser-session/allow";
const HEARTBEAT_URL = "http://127.0.0.1:8765/extension-heartbeat";
const POLL_MS = 3000;
const BLOCK_RULE_ID = 1;
const ALLOW_RULE_START = 100;
const HEARTBEAT_ALARM = "purity-extension-heartbeat";
const HEARTBEAT_PERIOD_MINUTES = 0.5;

let currentSession = { is_active: false };
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

function normalizeUrl(url) {
  try {
    return new URL(url).toString();
  } catch {
    return "";
  }
}

function buildRules(session) {
  const rules = [buildBlockRule()];

  let nextId = ALLOW_RULE_START;
  for (const domain of session.allowed_domains || []) {
    rules.push({
      id: nextId++,
      priority: 20,
      action: { type: "allow" },
      condition: {
        // requestDomains matches the exact domain and all subdomains without regex.
        requestDomains: [domain],
        resourceTypes: ["main_frame"]
      }
    });
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
  if (!currentSession.is_active) {
    await replaceRules([buildBlockRule()]);
    return;
  }
  await replaceRules(buildRules(currentSession));
}

function updateFromSession() {
  ruleUpdateChain = ruleUpdateChain
    .catch(() => {})
    .then(() => syncRulesFromSession());
  return ruleUpdateChain;
}

function isAllowedHostname(hostname, allowedDomains) {
  const host = (hostname || "").toLowerCase();
  return (allowedDomains || []).some(
    (domain) => host === domain || host.endsWith("." + domain)
  );
}

function isBlockedCandidate(url) {
  if (!currentSession.is_active) {
    return false;
  }
  if (!/^https?:/i.test(url || "")) {
    return false;
  }
  try {
    const hostname = new URL(url).hostname;
    return !isAllowedHostname(hostname, currentSession.allowed_domains);
  } catch {
    return true;
  }
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
  if (isBlockedCandidate(details.url)) {
    blockedByTabId.set(details.tabId, normalizeUrl(details.url));
  }
});

chrome.runtime.onInstalled.addListener(() => {
  scheduleHeartbeatAlarm();
  void sendHeartbeat();
  void updateFromSession();
});
chrome.runtime.onStartup.addListener(() => {
  scheduleHeartbeatAlarm();
  void sendHeartbeat();
  void updateFromSession();
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === HEARTBEAT_ALARM) {
    void sendHeartbeat();
  }
});
scheduleHeartbeatAlarm();
void sendHeartbeat();
void updateFromSession();
setInterval(() => {
  void updateFromSession();
}, POLL_MS);

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

  if (message?.type === "get-blocked-url") {
    sendResponse({ url: blockedByTabId.get(sender.tab?.id) || "" });
    return;
  }

  if (message?.type === "allow-blocked-url") {
    const blockedUrl = message.url || blockedByTabId.get(sender.tab?.id);
    if (!blockedUrl) {
      sendResponse({ ok: false });
      return;
    }

    fetch(ALLOW_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: blockedUrl })
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("allow failed");
        }
        const payload = await response.json();
        const allowedDomains = Array.isArray(payload?.allowed_domains) ? payload.allowed_domains : [];
        let blockedHostname = "";
        try { blockedHostname = new URL(blockedUrl).hostname; } catch {}
        if (!payload?.is_active || !blockedHostname || !allowedDomains.includes(blockedHostname)) {
          throw new Error("allow rejected");
        }
        await sendHeartbeat();
        await updateFromSession();
        const tabId = sender.tab?.id;
        if (typeof tabId === "number") {
          blockedByTabId.delete(tabId);
          await chrome.tabs.update(tabId, { url: blockedUrl });
        }
        sendResponse({ ok: true });
      })
      .catch(() => sendResponse({ ok: false }));

    return true;
  }
});