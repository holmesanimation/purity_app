function parseHash() {
  const hash = window.location.hash.slice(1); // strip leading #
  const params = new URLSearchParams(hash);
  return {
    reason:  params.get("reason") || "",
    query:   params.get("query")  ? decodeURIComponent(params.get("query")) : "",
    matches: params.get("matches") ? decodeURIComponent(params.get("matches")) : "",
    url:    params.get("url")    ? decodeURIComponent(params.get("url"))
            // legacy format: #url=<encoded>
            : (window.location.hash.startsWith("#url=") ? decodeURIComponent(window.location.hash.slice(5)) : "")
  };
}

document.addEventListener("DOMContentLoaded", async () => {
  const { reason, query, matches, url } = parseHash();

  if (reason === "query-warn") {
    // Search query soft-risk warning mode
    document.getElementById("query-warn").style.display = "block";
    document.getElementById("warn-query").textContent = "\u201c" + (query || "this search") + "\u201d";
    if (matches) {
      document.getElementById("warn-matches").textContent = "Flagged word: " + matches;
    }
    document.getElementById("warn-back-btn").addEventListener("click", () => {
      if (history.length > 1) { history.back(); } else { window.close(); }
    });
    document.getElementById("warn-proceed-btn").addEventListener("click", () => {
      if (!url) {
        history.back();
        return;
      }
      chrome.runtime.sendMessage(
        { type: "approve-soft-risk-search", url },
        (response) => {
          if (chrome.runtime.lastError || !response?.approved) {
            console.error(
              "Purity could not approve this search:",
              chrome.runtime.lastError?.message || "No approval response."
            );
            return;
          }
          window.location.replace(url);
        }
      );
    });
  } else if (reason === "query") {
    // Search query block mode
    document.getElementById("query-block").style.display = "block";
    document.getElementById("blocked-query").textContent = "\u201c" + (query || "blocked search") + "\u201d";
    if (matches) {
      document.getElementById("blocked-matches").textContent = "Flagged word: " + matches;
    }
    document.getElementById("query-back-btn").addEventListener("click", () => {
      if (history.length > 1) {
        history.back();
      } else {
        window.close();
      }
    });
  } else if (reason === "blacklisted") {
    // URL blacklist block mode
    document.getElementById("blacklisted-block").style.display = "block";
    document.getElementById("blacklisted-url").textContent = url || "Unknown URL";
    document.getElementById("blacklisted-back-btn").addEventListener("click", () => {
      if (history.length > 1) { history.back(); } else { window.close(); }
    });
  } else {
    // No active session (default fallback)
    document.getElementById("url-block").style.display = "block";
    document.getElementById("blocked-url").textContent = url || "";
    document.getElementById("no-session-back-btn").addEventListener("click", () => {
      if (history.length > 1) { history.back(); } else { window.close(); }
    });
  }
});