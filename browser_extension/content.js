// content.js — Input monitoring, debounce, and form interception.
// Depends on overlay.js (window.PurityApp) being loaded first.

(function () {
  'use strict';

  const DEBOUNCE_MS = 500;

  // Tracks elements whose next synthetic Enter keydown should be passed through
  // after a SAFE classification re-fire (for contenteditable search boxes with no form).
  const enterBypass = new WeakSet();

  // ── Utilities ────────────────────────────────────────────────────────────────

  function debounce(fn, ms) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  /**
   * Read the current text value from an input-like element.
   * Returns full text; the classifier performs its own recent-word extraction.
   * @param {Element} el
   * @returns {string}
   */
  function extractText(el) {
    if (el.isContentEditable) {
      return el.textContent || '';
    }
    return el.value || '';
  }

  // ── Re-submission helper ──────────────────────────────────────────────────────

  // ── Classification ────────────────────────────────────────────────────────────

  /**
   * Send text to the background service worker for classification.
   * IMPORTANT: any event blocking must be done BEFORE this call (synchronously).
   * @param {string} text
   * @param {function|null} onSafe  Called when classification is SAFE or the user
   *                                chooses to proceed after a SOFT_RISK warning.
   *                                Pass null for debounced-input calls (no navigation to restore).
   */
  function sendForClassification(text, onSafe) {
    if (!text || text.trim().length < 3) {
      if (onSafe) onSafe();
      return;
    }

    chrome.runtime.sendMessage(
      { type: 'classify', text, url: location.href },
      (response) => {
        if (chrome.runtime.lastError) return; // Extension reloaded, etc.
        if (!response || response.level === 'SAFE') {
          if (onSafe) onSafe();
          return;
        }

        if (response.level === 'SOFT_RISK') {
          // onDismiss = no-op (user chose not to proceed)
          // onProceed = onSafe (user acknowledges warning and continues)
          window.PurityApp.showSoftRisk(text, () => {}, onSafe || null);
        } else if (response.level === 'HARD_BLOCK') {
          window.PurityApp.showHardBlock(text);
          // FUTURE: PurityApp.onHardBlock hook is called inside showHardBlock
        }
      }
    );
  }

  // ── Listener attachment ──────────────────────────────────────────────────────

  /**
   * Attach a debounced input listener and submission interceptor to an element.
   * Guards against double-attach with a dataset flag.
   * @param {Element} el
   */
  function attachListener(el) {
    if (el.dataset.purityAttached === '1') return;
    el.dataset.purityAttached = '1';

    // Debounced typing warning (no navigation to restore — onSafe is null).
    const handleInput = debounce(() => {
      sendForClassification(extractText(el), null);
    }, DEBOUNCE_MS);

    el.addEventListener('input', handleInput);

    interceptSubmission(el);
  }

  /**
   * Attach form-submit and Enter-key interceptors.
   * Events are blocked SYNCHRONOUSLY; classification runs async; re-submission
   * is triggered via onSafe callback if the text is clean.
   * @param {Element} el
   */
  function interceptSubmission(el) {
    // Enter-key interception for search/combobox inputs whose submit may be
    // handled by page JS rather than a native form submission.
    const isSearchLike =
      el.getAttribute('type') === 'search' ||
      el.getAttribute('role') === 'searchbox' ||
      el.getAttribute('role') === 'combobox';

    if (isSearchLike && !el.dataset.purityEnterGuarded) {
      el.dataset.purityEnterGuarded = '1';
      el.addEventListener('keydown', (evt) => {
        if (evt.key !== 'Enter') return;

        // Allow the re-fired synthetic event through after a SAFE classification
        // (only used when there is no <form> to call form.submit() on).
        if (enterBypass.has(el)) {
          enterBypass.delete(el);
          return;
        }

        // Block SYNCHRONOUSLY before any async work.
        // stopImmediatePropagation prevents page JS (e.g. Google's search handler)
        // from receiving this event even if it is also listening in capture phase.
        evt.preventDefault();
        evt.stopImmediatePropagation();

        const text = extractText(el);
        sendForClassification(text, () => {
          const form = el.closest('form');
          if (form) {
            // form.submit() does NOT fire the submit event — bypasses our listener.
            form.submit();
          } else {
            // No form (e.g. standalone contenteditable search box): re-fire Enter.
            enterBypass.add(el);
            el.dispatchEvent(new KeyboardEvent('keydown', {
              key: 'Enter', code: 'Enter', keyCode: 13,
              bubbles: true, cancelable: true
            }));
          }
        });
      }, true); // Capture phase.
    }
  }

  // ── DOM observation ──────────────────────────────────────────────────────────

  const INPUT_SELECTOR = 'input:not([type="hidden"]):not([type="password"]):not([type="file"]), textarea, [contenteditable="true"], [contenteditable=""]';

  function scanAndAttach(root) {
    root.querySelectorAll(INPUT_SELECTOR).forEach(attachListener);
  }

  function observeInputs() {
    scanAndAttach(document);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) continue;
          if (node.matches(INPUT_SELECTOR)) {
            attachListener(node);
          }
          scanAndAttach(node);
        }
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  // ── Page content scan ────────────────────────────────────────────────────────

  /**
   * One-time scan of the page's visible text against weight-100 hard_block phrases.
   * If a match is found, shows a content-warning overlay with go-back / proceed options.
   * Capped at 100 000 characters to avoid sending enormous strings to the service worker.
   */
  const PAGE_SCAN_CHAR_LIMIT = 100000;
  let pageScanDone = false;

  function scanPageContent() {
    if (pageScanDone) return;
    pageScanDone = true;

    const text = (document.body?.innerText || '').slice(0, PAGE_SCAN_CHAR_LIMIT);
    if (!text || text.trim().length < 3) return;

    chrome.runtime.sendMessage(
      { type: 'classify_page_content', text },
      (response) => {
        if (chrome.runtime.lastError) return;
        if (!response || !response.found || !response.matches.length) return;

        const firstMatch = response.matches[0].phrase;
        window.PurityApp.showPageContentWarning(
          firstMatch,
          () => { window.history.back(); },
          () => {} // proceed: close overlay and stay on page
        );
      }
    );
  }

  // Start monitoring once the DOM is available.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      observeInputs();
      scanPageContent();
    });
  } else {
    observeInputs();
    scanPageContent();
  }
}());
