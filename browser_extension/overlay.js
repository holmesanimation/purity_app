// overlay.js — Overlay UI injected into pages by the Purity extension.
// Loaded as a content script before content.js.
// Exposes window.PurityApp with showSoftRisk, showHardBlock, removeOverlay, onHardBlock.

(function () {
  'use strict';

  // Guard: only inject the CSS once per page.
  let cssInjected = false;

  function injectCSS() {
    if (cssInjected) return;
    cssInjected = true;

    const style = document.createElement('style');
    style.id = 'purity-overlay-styles';
    style.textContent = `
      .purity-overlay-backdrop {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        z-index: 2147483647;
        display: flex;
        align-items: flex-start;
        justify-content: center;
        padding-top: 48px;
        background: rgba(0, 0, 0, 0.55);
        font-family: Georgia, "Palatino Linotype", serif;
      }

      .purity-overlay-card {
        width: min(520px, calc(100vw - 32px));
        padding: 28px 32px;
        border-radius: 18px;
        background: #fffdfa;
        border: 1px solid #d8d0c3;
        box-shadow: 0 18px 48px rgba(47, 42, 36, 0.20);
        color: #2f2a24;
        position: relative;
        z-index: 2147483647;
      }

      .purity-overlay-badge-warn {
        display: inline-block;
        margin: 0 0 14px;
        padding: 4px 12px;
        border-radius: 999px;
        background: #fdf0e6;
        border: 1px solid #e8c9a0;
        color: #8b4513;
        font-size: 0.82rem;
        letter-spacing: 0.03em;
      }

      .purity-overlay-badge-block {
        display: inline-block;
        margin: 0 0 14px;
        padding: 4px 12px;
        border-radius: 999px;
        background: #fde8e8;
        border: 1px solid #e8a0a0;
        color: #8b0000;
        font-size: 0.82rem;
        letter-spacing: 0.03em;
      }

      .purity-overlay-title-warn {
        margin: 0 0 10px;
        font-size: 1.4rem;
        color: #8b4513;
      }

      .purity-overlay-title-block {
        margin: 0 0 10px;
        font-size: 1.4rem;
        color: #8b0000;
      }

      .purity-overlay-body {
        margin: 0 0 10px;
        line-height: 1.6;
        color: #6d655b;
        font-size: 0.95rem;
      }

      .purity-overlay-scripture {
        margin: 14px 0 20px;
        padding: 12px 16px;
        border-radius: 12px;
        background: #f6f2e8;
        border: 1px solid #d8d0c3;
        color: #6d655b;
        font-style: italic;
        line-height: 1.7;
        font-size: 0.92rem;
      }

      .purity-overlay-scripture cite {
        display: block;
        margin-top: 6px;
        font-style: normal;
        font-size: 0.82rem;
        color: #315c3c;
      }

      .purity-overlay-dismiss {
        display: inline-block;
        padding: 10px 22px;
        border-radius: 8px;
        background: #315c3c;
        color: #fff;
        font-family: Georgia, "Palatino Linotype", serif;
        font-size: 0.92rem;
        border: none;
        cursor: pointer;
        text-decoration: none;
      }

      .purity-overlay-dismiss:hover {
        background: #274a2f;
      }

      .purity-overlay-proceed {
        display: inline-block;
        margin-left: 10px;
        padding: 10px 22px;
        border-radius: 8px;
        background: transparent;
        color: #6d655b;
        font-family: Georgia, "Palatino Linotype", serif;
        font-size: 0.92rem;
        border: 1px solid #d8d0c3;
        cursor: pointer;
      }

      .purity-overlay-proceed:hover {
        background: #f6f2e8;
      }

      .purity-overlay-close {
        position: absolute;
        top: 14px;
        right: 16px;
        background: none;
        border: none;
        font-size: 1.2rem;
        color: #6d655b;
        cursor: pointer;
        line-height: 1;
        padding: 4px 6px;
        border-radius: 4px;
      }

      .purity-overlay-close:hover {
        background: #f0ece2;
      }
    `;
    document.head.appendChild(style);
  }

  function removeOverlay() {
    const existing = document.getElementById('purity-overlay-root');
    if (existing) existing.remove();
  }

  const SCRIPTURE_QUOTE =
    '\u201cWhatever is true, whatever is honorable, whatever is just, whatever is pure, ' +
    'whatever is lovely, whatever is commendable \u2014 if there is any excellence, if there is ' +
    'anything worthy of praise, think about these things.\u201d';
  const SCRIPTURE_CITE = '\u2014 Philippians 4:8';

  function buildCard({ badgeClass, titleClass, badgeText, titleText, bodyText, showDismiss, onDismiss, onProceed }) {
    injectCSS();
    removeOverlay();

    const backdrop = document.createElement('div');
    backdrop.id = 'purity-overlay-root';
    backdrop.className = 'purity-overlay-backdrop';

    const card = document.createElement('div');
    card.className = 'purity-overlay-card';

    // Always show a close (×) button so the overlay can be dismissed in all cases.
    const closeBtn = document.createElement('button');
    closeBtn.className = 'purity-overlay-close';
    closeBtn.textContent = '\u00d7';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.addEventListener('click', removeOverlay);
    card.appendChild(closeBtn);

    const badge = document.createElement('span');
    badge.className = badgeClass;
    badge.textContent = badgeText;

    const title = document.createElement('h2');
    title.className = titleClass;
    title.textContent = titleText;

    const body = document.createElement('p');
    body.className = 'purity-overlay-body';
    body.textContent = bodyText;

    const scripture = document.createElement('blockquote');
    scripture.className = 'purity-overlay-scripture';
    scripture.textContent = SCRIPTURE_QUOTE;
    const cite = document.createElement('cite');
    cite.textContent = SCRIPTURE_CITE;
    scripture.appendChild(cite);

    card.appendChild(badge);
    card.appendChild(title);
    card.appendChild(body);
    card.appendChild(scripture);

    if (showDismiss) {
      const btn = document.createElement('button');
      btn.className = 'purity-overlay-dismiss';
      btn.textContent = 'I choose better';
      btn.addEventListener('click', () => {
        removeOverlay();
        if (typeof onDismiss === 'function') onDismiss();
      });
      card.appendChild(btn);

      if (typeof onProceed === 'function') {
        const proceedBtn = document.createElement('button');
        proceedBtn.className = 'purity-overlay-proceed';
        proceedBtn.textContent = 'Search anyway';
        proceedBtn.addEventListener('click', () => {
          removeOverlay();
          onProceed();
        });
        card.appendChild(proceedBtn);
      }
    }

    backdrop.appendChild(card);
    document.body.appendChild(backdrop);
  }

  window.PurityApp = {
    /**
     * Show a dismissible soft-risk warning overlay.
     * @param {string} matchedText  The text that triggered the warning.
     * @param {function} onDismiss  Called when the user dismisses the overlay.
     */
    showSoftRisk(matchedText, onDismiss, onProceed) {
      buildCard({
        badgeClass: 'purity-overlay-badge-warn',
        titleClass: 'purity-overlay-title-warn',
        badgeText: 'Pause & Reflect',
        titleText: 'Heads up',
        bodyText: 'What you\u2019re searching for may lead somewhere you don\u2019t want to go.',
        showDismiss: true,
        onDismiss,
        onProceed: onProceed || null
      });
    },

    /**
     * Show a hard-block overlay. No proceed option.
     * Calls PurityApp.onHardBlock(matchedText) if set.
     * @param {string} matchedText
     */
    showHardBlock(matchedText) {
      buildCard({
        badgeClass: 'purity-overlay-badge-block',
        titleClass: 'purity-overlay-title-block',
        badgeText: 'Blocked',
        titleText: 'Not this way',
        bodyText: 'This search has been blocked to help you stay on track.',
        showDismiss: false,
        onDismiss: null
      });

      // FUTURE: assign this in a future Purity panic workflow hook
      // e.g. PurityApp.onHardBlock = (text) => chrome.runtime.sendMessage({type: 'trigger-panic', text})
      if (typeof window.PurityApp.onHardBlock === 'function') {
        window.PurityApp.onHardBlock(matchedText);
      }
    },

    removeOverlay,

    /** Assign to hook into the hard-block event from external content scripts. */
    onHardBlock: null
  };
}());
