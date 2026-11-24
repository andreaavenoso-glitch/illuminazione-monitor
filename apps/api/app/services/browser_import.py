"""Portals that refuse the server's address (dgegovpa.it, halleyweb.com): the pages are read by the user's own browser.

``SCRIPT`` is pasted in the browser console while the portal page is open. It reads that page and the pages it links to
that look relevant (same site, so the browser may read them), and downloads ``monitor_pagine.json`` for the app.
"""
from __future__ import annotations

import re
import unicodedata

SCRIPT = r"""(async () => {
  const MAX = 40, PAUSA = 400;
  const KW = /illumin|luce|energia|ppp|partenariato|finanza.?di.?progetto|project.?financing|concession|manifestazion|avviso|delibera|determina|bando|gara|proposta|esito|affidament/i;
  const NO = /\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|p7m)(\?|$)|login|logout|mailto:|tel:|javascript:/i;
  const origin = location.origin, seen = new Set(), pagine = [];
  const norm = u => { try { const x = new URL(u, location.href); x.hash = ''; return x.href; } catch (e) { return null; } };
  const links = (html, base) => [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll('a[href]')]
    .map(a => ({ u: norm(a.getAttribute('href'), base), t: (a.textContent || '').replace(/\s+/g, ' ').trim() }))
    .filter(x => x.u && x.u.startsWith(origin) && !NO.test(x.u) && (KW.test(x.t) || KW.test(x.u)));
  const leggi = async u => { try { const r = await fetch(u, { credentials: 'include' }); return r.ok ? await r.text() : null; } catch (e) { return null; } };
  const aggiungi = (u, html) => { if (u && html && !seen.has(u)) { seen.add(u); pagine.push({ url: u, html }); } };
  aggiungi(norm(location.href), document.documentElement.outerHTML);
  let coda = links(pagine[0].html, location.href), livello = 0;
  while (coda.length && pagine.length < MAX && livello < 2) {
    const prossimi = [];
    for (const l of coda) {
      if (pagine.length >= MAX) break;
      if (seen.has(l.u)) continue;
      const html = await leggi(l.u);
      if (html) { aggiungi(l.u, html); if (livello === 0) prossimi.push(...links(html, l.u)); }
      await new Promise(r => setTimeout(r, PAUSA));
    }
    coda = prossimi; livello++;
  }
  const blob = new Blob([JSON.stringify({ origine: location.href, pagine })], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'monitor_pagine.json'; a.click();
  console.log('Monitor: ' + pagine.length + ' pagine salvate in monitor_pagine.json. Caricalo nell\'app.');
})();"""


def _fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).strip()


def pick_comune(candidates: list[tuple[object, str]], wanted: str) -> tuple[object | None, list[str]]:
    """(item, other matching names). Exact name first, then the only name that contains the text; None when there is
    no match or more than one (the names are then returned so the user can be more precise). Pure, tested."""
    w = _fold(wanted)
    if not w:
        return None, []
    exact = [c for c in candidates if _fold(c[1]) in (w, "comune di " + w)]
    if len(exact) == 1:
        return exact[0][0], []
    part = exact or [c for c in candidates if w in _fold(c[1])]
    if len(part) == 1:
        return part[0][0], []
    return None, sorted({c[1] for c in part})[:8]
