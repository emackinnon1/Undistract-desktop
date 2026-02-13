let port = null;
let blockingEnabled = false;
let domains = [];

function connect() {
  port = browser.runtime.connectNative("undistract.native_host");
  port.onMessage.addListener((msg) => {
    if (msg.type === "state") {
      blockingEnabled = !!msg.blocking;
      domains = Array.isArray(msg.domains) ? msg.domains : [];
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

function isBlocked(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return domains.some(d => {
      const dom = normalizeDomain(d);
      return host === dom || host.endsWith(`.${dom}`);
    });
  } catch (_) {
    return false;
  }
}

function onBeforeRequest(details) {
  if (!blockingEnabled) return {};
  if (isBlocked(details.url)) {
    return { cancel: true };
  }
  return {};
}

browser.webRequest.onBeforeRequest.addListener(
  onBeforeRequest,
  { urls: ["<all_urls>"] },
  ["blocking"]
);

connect();
