"""Portals that refuse the server's address (dgegovpa.it, halleyweb.com): the pages are read by the user's own browser.

``SCRIPT`` is pasted in the browser console while the portal page is open. It reads that page and the pages it links to
that look relevant (same site, so the browser may read them), and downloads ``monitor_pagine.json`` for the app.
"""
from __future__ import annotations

import re
import unicodedata

SCRIPT = r"""(async () => {
  const O = Object.assign({ MAX: 300, CHUNK: 60, PAUSA: 400, LISTE: 40 }, window.MONITOR_OPZIONI || {});
  const KW = /illumin|luce|energia|ppp|partenariato|finanza.?di.?progetto|project.?financing|concession|manifestazion|avviso|delibera|determina|bando|gara|proposta|esito|affidament|procedura|contratt/i;
  const NO = /\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|p7m)(\?|$)|login|logout|mailto:|tel:|javascript:/i;
  const PAG = /^(\d{1,3}|succ(essiv[oa])?|avanti|prossim[oa]|next|»|›|>|>>)$/i;
  const origin = location.origin, seen = new Set(), pagine = [];
  const norm = u => { try { const x = new URL(u, location.href); x.hash = ''; return x.href; } catch (e) { return null; } };
  const percorso = u => { try { const x = new URL(u); return x.origin + x.pathname.replace(/\/+$/, ''); } catch (e) { return ''; } };
  const doc = html => new DOMParser().parseFromString(html, 'text/html');
  const ancore = (html, base) => [...doc(html).querySelectorAll('a[href]')].map(a => ({ u: norm(a.getAttribute('href'), base), t: (a.textContent || '').replace(/\s+/g, ' ').trim() }))
    .filter(x => x.u && x.u.startsWith(origin) && !/^(javascript|mailto|tel):/i.test(x.u));
  const dettagli = (html, base) => ancore(html, base).filter(x => !NO.test(x.u) && (KW.test(x.t) || KW.test(x.u)));
  const sfoglia = (html, base) => ancore(html, base).filter(x => PAG.test(x.t) && percorso(x.u) === percorso(base));
  const leggi = async u => { try { const r = await fetch(u, { credentials: 'include' }); return r.ok ? await r.text() : null; } catch (e) { return null; } };
  const pausa = () => new Promise(r => setTimeout(r, O.PAUSA));
  const aggiungi = (u, html) => { if (u && html && !seen.has(u)) { seen.add(u); pagine.push({ url: u, html }); return true; } return false; };
  const avanza = () => { if (pagine.length % 10 === 0) console.log('Monitor: ' + pagine.length + ' pagine lette…'); };

  const inizio = norm(location.href);
  aggiungi(inizio, document.documentElement.outerHTML);
  // 1) le pagine dell'elenco (1, 2, 3, successiva…), una dopo l'altra
  const liste = [{ u: inizio, html: pagine[0].html }];
  const codaListe = sfoglia(pagine[0].html, inizio).map(x => x.u);
  while (codaListe.length && liste.length < O.LISTE && pagine.length < O.MAX) {
    const u = codaListe.shift();
    if (seen.has(u)) continue;
    const html = await leggi(u);
    if (!html) continue;
    aggiungi(u, html); liste.push({ u, html }); avanza();
    sfoglia(html, u).forEach(x => { if (!seen.has(x.u)) codaListe.push(x.u); });
    await pausa();
  }
  // 2) i dettagli collegati dalle pagine dell'elenco
  const dett = [];
  for (const l of liste) dettagli(l.html, l.u).forEach(x => { if (!seen.has(x.u) && !dett.includes(x.u)) dett.push(x.u); });
  const secondo = [];
  for (const u of dett) {
    if (pagine.length >= O.MAX) break;
    const html = await leggi(u);
    if (html && aggiungi(u, html)) { avanza(); dettagli(html, u).forEach(x => secondo.push(x.u)); }
    await pausa();
  }
  // 3) un secondo livello (allegati e proposte collegate ai dettagli)
  for (const u of secondo) {
    if (pagine.length >= O.MAX) break;
    if (seen.has(u)) continue;
    const html = await leggi(u);
    if (html) { aggiungi(u, html); avanza(); }
    await pausa();
  }
  // 4) i file, a gruppi (il server ne accetta fino a 80 pagine alla volta)
  const gruppi = [];
  for (let i = 0; i < pagine.length; i += O.CHUNK) gruppi.push(pagine.slice(i, i + O.CHUNK));
  for (let n = 0; n < gruppi.length; n++) {
    const blob = new Blob([JSON.stringify({ origine: location.href, pagine: gruppi[n] })], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'monitor_pagine_' + String(n + 1).padStart(2, '0') + 'di' + String(gruppi.length).padStart(2, '0') + '.json';
    a.click();
    await new Promise(r => setTimeout(r, 700));
  }
  console.log('Monitor: ' + pagine.length + ' pagine (' + liste.length + ' di elenco) in ' + gruppi.length + ' file. Se Chrome chiede di consentire download multipli, accetta. Caricali tutti nell\'app.');
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
