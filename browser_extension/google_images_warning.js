function getTargetUrl() {
  const hash = window.location.hash;
  return hash.startsWith("#url=") ? decodeURIComponent(hash.slice(5)) : "";
}

document.addEventListener("DOMContentLoaded", () => {
  const url = getTargetUrl();
  const yesBtn = document.getElementById("yes-btn");
  const noBtn = document.getElementById("no-btn");

  yesBtn.addEventListener("click", () => {
    if (url) {
      window.location.href = url;
    }
  });

  noBtn.addEventListener("click", () => {
    window.close();
  });
});
