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
    const escapedDomain = domain.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    rules.push({
      id: nextId++,
      priority: 20,
      action: { type: "allow" },
      condition: {
        // Match the exact domain and any subdomain (e.g. www.gods-design.com).
        regexFilter: `^https?://([^/]*\.)?${escapedDomain}(/.*)?$`,
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

chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  if (details.frameId !== 0) {
    return;
  }
  if (details.url.startsWith(chrome.runtime.getURL("blocked.html"))) {
    return;
  }
  void sendHeartbeat();
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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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