function parseHash() {
  const hash = window.location.hash.slice(1); // strip leading #
  const params = new URLSearchParams(hash);
  return {
    reason: params.get("reason") || "",
    query:  params.get("query")  ? decodeURIComponent(params.get("query")) : "",
    url:    params.get("url")    ? decodeURIComponent(params.get("url"))
            // legacy format: #url=<encoded>
            : (window.location.hash.startsWith("#url=") ? decodeURIComponent(window.location.hash.slice(5)) : "")
  };
}

async function allowBlockedUrl(url) {
  const response = await chrome.runtime.sendMessage({ type: "allow-blocked-url", url });
  return Boolean(response?.ok);
}

document.addEventListener("DOMContentLoaded", async () => {
  const { reason, query, url } = parseHash();

  if (reason === "query-warn") {
    // Search query soft-risk warning mode
    document.getElementById("query-warn").style.display = "block";
    document.getElementById("warn-query").textContent = "\u201c" + (query || "this search") + "\u201d";
    document.getElementById("warn-back-btn").addEventListener("click", () => {
      if (history.length > 1) { history.back(); } else { window.close(); }
    });
    document.getElementById("warn-proceed-btn").addEventListener("click", () => {
      if (url) { window.location.replace(url); } else { history.back(); }
    });
  } else if (reason === "query") {
    // Search query block mode
    document.getElementById("query-block").style.display = "block";
    document.getElementById("blocked-query").textContent = "\u201c" + (query || "blocked search") + "\u201d";
    document.getElementById("query-back-btn").addEventListener("click", () => {
      if (history.length > 1) {
        history.back();
      } else {
        window.close();
      }
    });
  } else {
    // URL whitelist block mode
    document.getElementById("url-block").style.display = "block";
    const urlLabel = document.getElementById("blocked-url");
    const yesBtn = document.getElementById("yes-btn");
    const noBtn = document.getElementById("no-btn");

    urlLabel.textContent = url || "Unknown URL";

    yesBtn.addEventListener("click", async () => {
      yesBtn.disabled = true;
      noBtn.disabled = true;
      const ok = await allowBlockedUrl(url);
      if (!ok) {
        yesBtn.disabled = false;
        noBtn.disabled = false;
      }
    });

    noBtn.addEventListener("click", () => {
      window.close();
    });
  }
});