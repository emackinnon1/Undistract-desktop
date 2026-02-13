let port = null;
let blockingEnabled = false;
let domains = [];

function connect() {
  port = chrome.runtime.connectNative("undistract.native_host");
  port.onMessage.addListener((msg) => {
    if (msg.type === "state") {
      blockingEnabled = !!msg.blocking;
      domains = Array.isArray(msg.domains) ? msg.domains : [];
      updateRules();
    }
  });
  port.onDisconnect.addListener(() => {
    setTimeout(connect, 2000);
  });
  port.postMessage({ type: "request_state" });
}

function normalizeDomain(d) {
  return d.trim().toLowerCase();
}

function buildRules(domainsList) {
  const rules = [];
  let id = 1;
  for (const domain of domainsList) {
    const host = normalizeDomain(domain);
    if (!host) continue;
    rules.push({
      id: id++,
      priority: 1,
      action: { type: "block" },
      condition: {
        urlFilter: `||${host}^`,
        resourceTypes: [
          "main_frame",
          "sub_frame",
          "xmlhttprequest",
          "script",
          "image",
          "stylesheet",
          "font",
          "media",
          "object"
        ]
      }
    });
  }
  return rules;
}

async function updateRules() {
  if (!blockingEnabled) {
    const current = await chrome.declarativeNetRequest.getDynamicRules();
    const ids = current.map(r => r.id);
    if (ids.length) {
      await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: ids, addRules: [] });
    }
    return;
  }
  const rules = buildRules(domains);
  const current = await chrome.declarativeNetRequest.getDynamicRules();
  const ids = current.map(r => r.id);
  await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: ids, addRules: rules });
}

connect();
