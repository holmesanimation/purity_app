function getBlockedUrl() {
  const hash = window.location.hash;
  return hash.startsWith("#url=") ? hash.slice(5) : "";
}

async function allowBlockedUrl(url) {
  const response = await chrome.runtime.sendMessage({ type: "allow-blocked-url", url });
  return Boolean(response?.ok);
}

document.addEventListener("DOMContentLoaded", async () => {
  const url = getBlockedUrl();
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
});