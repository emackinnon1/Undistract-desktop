let port = null;
let blockingEnabled = false;
let domains = [];

const DEBUG = true;
function log(...args) {
  if (DEBUG) console.log("[Undistract]", ...args);
}

function connect() {
  log("Connecting to native host...");
  port = chrome.runtime.connectNative("undistract.native_host");
  port.onMessage.addListener((msg) => {
    log("Native host message:", JSON.stringify(msg));
    if (msg.type === "state") {
      blockingEnabled = !!msg.blocking;
      domains = Array.isArray(msg.domains) ? msg.domains : [];
      log("State updated — blocking:", blockingEnabled, "domains:", domains);
      updateRules();
    }
  });
  port.onDisconnect.addListener(() => {
    log("Native host disconnected. lastError:", chrome.runtime.lastError?.message);
    port = null;
    setTimeout(connect, 2000);
  });
  port.postMessage({ type: "request_state" });
}

function normalizeDomain(d) {
  let host = d.trim().toLowerCase();
  // Strip scheme (http:// https://)
  host = host.replace(/^https?:\/\//, "");
  // Strip path, query, fragment
  host = host.replace(/[\/\?#].*$/, "");
  // Strip port
  host = host.replace(/:\d+$/, "");
  // Strip leading www.
  host = host.replace(/^www\./, "");
  return host;
}

function buildRules(domainsList) {
  const rules = [];
  let id = 1;
  for (const domain of domainsList) {
    const host = normalizeDomain(domain);
    if (!host) {
      log("Skipping empty domain from raw:", domain);
      continue;
    }
    const rule = {
      id: id++,
      priority: 1,
      action: { type: "block" },
      condition: {
        urlFilter: `||${host}`,
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
    };
    log("Built rule:", JSON.stringify(rule));
    rules.push(rule);
  }
  return rules;
}

async function updateRules() {
  const current = await chrome.declarativeNetRequest.getDynamicRules();
  log("Current DNR rules:", current.length, current.map(r => r.id));
  if (!blockingEnabled) {
    const ids = current.map(r => r.id);
    if (ids.length) {
      await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: ids, addRules: [] });
      log("Cleared all rules (blocking disabled)");
    }
    return;
  }
  const rules = buildRules(domains);
  const ids = current.map(r => r.id);
  try {
    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: ids, addRules: rules });
    log("Applied", rules.length, "blocking rules");
  } catch (err) {
    log("ERROR updating rules:", err.message);
  }
  // Verify what's actually active
  const active = await chrome.declarativeNetRequest.getDynamicRules();
  log("Active DNR rules after update:", JSON.stringify(active));
}

// Also log matched rules for debugging (requires declarativeNetRequestFeedback permission)
if (chrome.declarativeNetRequest.onRuleMatchedDebug) {
  chrome.declarativeNetRequest.onRuleMatchedDebug.addListener((info) => {
    log("RULE MATCHED:", info.request.url, "rule:", info.rule.ruleId);
  });
  log("onRuleMatchedDebug listener registered");
}

connect();
