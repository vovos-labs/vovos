// Heuristic detector for a consent interface on the current document.
// Runs in every frame; returns a plain JSON object. Pierces open shadow roots.
// Known blind spots: closed shadow roots, canvas-rendered banners, labels in
// languages/phrasings not covered by the patterns below. Contributions of
// additional patterns (especially Indian languages) are welcome.
() => {
  const CONTAINER_HINT = /(cookie|consent|gdpr|dpdp|cmp|onetrust|cookiebot|didomi|usercentrics|osano|termly|iubenda|truste|quantcast|privacy[-_ ]?(banner|notice|popup|modal|bar))/i;
  const CONSENT_TEXT = /(cookie|consent|personal data|privacy|tracking|सहमति|कुकी|गोपनीयता|व्यक्तिगत डेटा)/i;
  const ACCEPT = /^(accept|allow|i agree|agree|i accept|got it|ok\b|okay|yes\b|continue and accept|स्वीकार|सभी स्वीकार|सहमत|मैं सहमत)/i;
  const STRONG_ACCEPT = /^(accept all|accept cookies|accept all cookies|allow all|allow all cookies|allow cookies|i agree|i accept|agree and continue|accept and continue|सभी स्वीकार)/i;
  const REJECT = /(reject|decline|deny|refuse|disagree|do not accept|don't accept|necessary only|only necessary|essential only|only essential|strictly necessary|necessary cookies only|continue without|no,? thanks|अस्वीकार|मना|केवल आवश्यक)/i;
  const SETTINGS = /(settings|preferences|customi[sz]e|manage|options|choices|more info|सेटिंग|प्राथमिकता|प्रबंधित)/i;
  const NOTICE = /(privacy|notice|policy|data protection|गोपनीयता|सूचना|नीति)/i;
  const CLICKABLE = 'button,a,[role=button],input[type=button],input[type=submit]';

  const deepAll = (root, selector) => {
    const out = [];
    const walk = (node) => {
      node.querySelectorAll(selector).forEach((el) => out.push(el));
      node.querySelectorAll('*').forEach((el) => { if (el.shadowRoot) walk(el.shadowRoot); });
    };
    walk(root);
    return out;
  };
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.05;
  };
  const clean = (t, n = 120) => (t || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const label = (el) => clean(el.innerText || el.value || el.getAttribute('aria-label') || el.title || '');
  const hint = (el) => [el.id, typeof el.className === 'string' ? el.className : '', el.getAttribute('aria-label'),
    el.getAttribute('data-testid'), el.getAttribute('data-nosnippet') !== null ? 'nosnippet' : ''].join(' ');
  const floating = (el) => ['fixed', 'sticky'].includes(getComputedStyle(el).position);
  const isDialog = (el) => el.tagName === 'DIALOG' || /dialog/.test(el.getAttribute('role') || '');
  const isAccept = (t) => ACCEPT.test(t) && !REJECT.test(t);

  const buttonsIn = (container) => deepAll(container, CLICKABLE).filter(visible).map(label).filter(Boolean);

  // 1. Containers that look like a consent layer and offer an accept button.
  let detector = 'container';
  let candidates = deepAll(document, 'div,section,aside,dialog,form,footer,[role=dialog],[role=alertdialog],[role=region]')
    .filter((el) => visible(el))
    .filter((el) => CONTAINER_HINT.test(hint(el)) || ((isDialog(el) || floating(el)) && CONSENT_TEXT.test(el.innerText || '')))
    .filter((el) => buttonsIn(el).some(isAccept));

  // 2. Fallback: an unmistakable accept button, then its nearest floating/dialog ancestor.
  if (!candidates.length) {
    detector = 'fallback';
    for (const btn of deepAll(document, CLICKABLE).filter(visible)) {
      if (!STRONG_ACCEPT.test(label(btn))) continue;
      let node = btn.parentElement;
      for (let i = 0; node && i < 12; i++, node = node.parentElement) {
        if (floating(node) || isDialog(node) || CONTAINER_HINT.test(hint(node))) { candidates.push(node); break; }
      }
    }
  }
  if (!candidates.length) return { found: false };

  // Prefer the outermost candidate so first-layer buttons in sibling regions are included.
  const container = candidates.find((c) => !candidates.some((o) => o !== c && o.contains(c))) || candidates[0];
  const texts = buttonsIn(container);

  const toggles = deepAll(container, 'input[type=checkbox],[role=switch],[role=checkbox]')
    .filter((el) => visible(el) || (el.labels && [...el.labels].some(visible)) || visible(el.parentElement))
    .map((el) => ({
      label: clean(el.getAttribute('aria-label') || (el.labels && el.labels[0] && el.labels[0].innerText) || (el.parentElement && el.parentElement.innerText) || el.id, 80),
      checked: el.checked === true || el.getAttribute('aria-checked') === 'true',
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
    }));

  const noticeLinks = deepAll(container, 'a[href]')
    .filter((a) => NOTICE.test(label(a)) || NOTICE.test(a.getAttribute('href') || ''))
    .map((a) => ({ text: label(a), href: a.href }));

  return {
    found: true,
    detector,
    container: { tag: container.tagName.toLowerCase(), id: container.id || null, hint: clean(hint(container), 160), text_excerpt: clean(container.innerText, 400) },
    accept: texts.filter(isAccept),
    reject: texts.filter((t) => REJECT.test(t)),
    settings: texts.filter((t) => SETTINGS.test(t) && !isAccept(t) && !REJECT.test(t)),
    toggles,
    notice_links: noticeLinks,
  };
}
