"""The TEXTS of the Gate sheet, built from the fields of the analysis (pure functions, no PowerPoint).

Every statement that comes from a document ends with its reference, "[fonte: avviso.pdf (p. 3, 8)]": the sheet is a first
information to send by e-mail, and whoever reads it must be able to find each datum in the document it was read from. What is
not in the documents is "[da compilare]", never guessed.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.services.email_template import _campo

DC = "[da compilare]"
_FONTE = re.compile(r"^(?P<doc>.*?)(?:, p\. (?P<page>\d+))?$")


def it_num(n: float | int, dec: int = 0) -> str:
    s = f"{n:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(n: int, total: int) -> str:
    return f"{round(100 * n / total)}%" if total else "—"


def _short_doc(doc: str, n: int = 28) -> str:
    doc = doc.split(" › ")[-1]  # a file inside an archive: the file's own name says enough
    return doc if len(doc) <= n else doc[: n - 1].rstrip() + "…"


def refs(campi: dict, *keys: str, width: int = 28) -> str:
    """" [fonte: doc (p. 1, 3); other.pdf]" for the fields present, grouped by document; "" when none has a source."""
    by_doc: dict[str, list[int]] = {}
    for k in keys:
        f = (campi.get(k) or {}).get("fonte")
        if not f:
            continue
        m = _FONTE.match(f)
        pages = by_doc.setdefault(m.group("doc"), [])  # type: ignore[union-attr]
        if m.group("page") and int(m.group("page")) not in pages:  # type: ignore[union-attr]
            pages.append(int(m.group("page")))  # type: ignore[union-attr]
    if not by_doc:
        return ""
    parts = [f"{_short_doc(d, width)} (p. {', '.join(str(p) for p in sorted(ps))})" if ps else _short_doc(d, width) for d, ps in by_doc.items()]
    return f" [fonte: {'; '.join(parts)}]"


def _top(counts: dict[str, int], total: int, n: int = 3, label: Any = str.lower) -> str:
    return ", ".join(f"{label(k)} {_pct(v, total)} ({it_num(v)})" for k, v in list(counts.items())[:n])


def censimento_items(c: dict[str, Any], ref: str) -> list[tuple[str, str]]:
    """The lines of the "Desiderata e info Comune" slide that the census (the data set) answers."""
    n = c["apparecchi"]
    cons = f"{it_num(n)} apparecchi" + (f" su {it_num(c['centri_luminosi'])} centri luminosi" if c.get("centri_luminosi") else "")
    cons += f", {c['quadri']} quadri" if c.get("quadri") else ""
    items = [("Consistenza: ", cons + ref)]
    if c.get("sorgenti"):
        items.append(("Sorgenti: ", _top(c["sorgenti"], n, 3, str) + ref))
    reti = []
    if c.get("tipo_linea"):
        reti.append("linee " + _top(c["tipo_linea"], n, 2))
    if c.get("ore_annue"):
        reti.append(f"{it_num(c['ore_annue'])} ore annue di accensione")
    if reti:
        items.append(("Reti e quadri: ", "; ".join(reti) + ref))
    sost = []
    if c.get("materiale_sostegno"):
        sost.append("sostegni in " + _top(c["materiale_sostegno"], n, 2))
    if c.get("stato_sostegno"):
        sost.append("stato: " + ", ".join(f"{it_num(v)} {k.lower()}" for k, v in list(c["stato_sostegno"].items())[:3]))
    if c.get("altezza_media_m"):
        sost.append(f"altezza media {it_num(c['altezza_media_m'], 1)} m")
    if sost:
        items.append(("Sostegni: ", "; ".join(sost) + ref))
    if c.get("stato_apparecchio"):
        items.append(("Apparecchi: ", "stato: " + ", ".join(f"{it_num(v)} {k.lower()}" for k, v in list(c["stato_apparecchio"].items())[:3]) + ref))
    if c.get("ambito"):
        items.append(("Ambito illuminato: ", _top(c["ambito"], n, 2) + ref))
    if c.get("consumo_mwh"):
        items.append(("Consumi: ", f"~{it_num(c['consumo_mwh'])} MWh/anno (stima: {it_num(c['potenza_kw'], 1)} kW × {it_num(c['ore_annue'])} h)" + ref))
    return items


def desiderata_items(campi: dict) -> list[tuple[str, str]]:
    """Slide "Note di progetto (2 di 5) - Desiderata e info Comune": at most 14 lines, the ones the documents answer first."""
    c = (campi.get("censimento") or {}).get("valore")
    items: list[tuple[str, str]] = []
    if c:
        items += censimento_items(c, refs(campi, "censimento", width=22))
    else:
        pl = (campi.get("punti_luce") or {}).get("valore")
        items.append(("Consistenza: ", f"{pl} punti luce{refs(campi, 'punti_luce')}" if pl else DC))
        cons = (campi.get("consumi_mwh") or {}).get("valore")
        items.append(("Consumi: ", f"~{it_num(cons, 1)} MWh/anno{refs(campi, 'consumi_mwh')}" if cons else DC))
    conc = []
    if "durata" in campi:
        conc.append(str(campi["durata"]["valore"]))
    if "canone_annuo_eur" in campi:
        conc.append(f"canone di riferimento {_campo('canone_annuo_eur', campi['canone_annuo_eur']['valore'])}/anno (a base di gara, come scritto nel documento)")
    items.append(("Concessione: ", ("; ".join(conc) + refs(campi, "durata", "canone_annuo_eur")) if conc else DC))
    if "finanziamento" in campi:
        fin = str(campi["finanziamento"]["valore"])
        if "scadenza_finanziamento" in campi:
            d, _, ora = str(campi["scadenza_finanziamento"]["valore"]).partition(" ")
            fin += f"; domanda regionale entro il {date.fromisoformat(d):%d/%m/%Y}" + (f" ore {ora}" if ora else "")
        items.append(("Finanziamento: ", fin + refs(campi, "finanziamento", "scadenza_finanziamento")))
    else:
        items.append(("Finanziamento: ", DC))
    for key, label in (("requisiti", "Requisiti: "), ("criteri_valutazione", "Valutazione: "), ("criterio_aggiudicazione", "Criterio di aggiudicazione: ")):
        if key in campi:
            text = str(campi[key]["valore"])
            items.append((label, (text if len(text) <= 200 else text[:197].rstrip() + "…") + refs(campi, key)))
    if not any(k in campi for k in ("requisiti", "criteri_valutazione", "criterio_aggiudicazione")):
        items.append(("Requisiti e criteri di valutazione: ", DC))
    items.append(("Centro storico e vincoli: ", DC))
    items.append(("Servizi smart: ", DC))
    return items[:14]


def procedura_text(campi: dict, tipo: str, link: str | None = None) -> str:
    """Row "Procedura e perimetro" of the general data (it sits in a table with little room: short): kind of procedure, the
    main acts, who proposed it. Duration, fee and CIG are in the other slides."""
    proc = (campi.get("procedura") or {}).get("valore")
    bits = [tipo]
    keys = []
    if proc:
        bits.append("art. 193 D.Lgs. 36/2023, finanza di progetto" if isinstance(proc, list) and proc and "193" in proc[0] else
                    ", ".join(proc[:2]) if isinstance(proc, list) else str(proc))
        keys.append("procedura")
    atti = (campi.get("atti_citati") or {}).get("valore") or ([campi["atto_estremi"]["valore"]] if "atto_estremi" in campi else [])
    if atti:
        bits.append("atti: " + "; ".join(atti[:3]))
        keys += ["atti_citati", "atto_estremi"]
    if "proponente" in campi:
        p = campi["proponente"]["valore"]
        bits.append(f"su proposta di {p['nome']}" + (f" (prot. {p['protocollo']} del {p['data']})" if p.get("protocollo") else ""))
        keys.append("proponente")
    return " – ".join(bits) + refs(campi, *keys, width=22)


def informazioni_items(campi: dict, tipo: str, link: str | None, documenti: list[dict], scad: date | None, nota: str | None) -> list[tuple[str, str]]:
    """Slide "Note di progetto (1 di 5) - Informazioni fornite dall'amministrazione": what the notice itself says it provides."""
    items: list[tuple[str, str]] = [(f"{tipo}: ", link or DC)]
    for doc in documenti[:3]:
        items.append((f"{(doc.get('nome') or 'Documento')[:40]}: ", doc.get("url") or ""))
    if "atti_citati" in campi:
        items.append(("Atti richiamati: ", "; ".join(campi["atti_citati"]["valore"][:5]) + refs(campi, "atti_citati")))
    if "allegati_citati" in campi:
        items.append(("Allegati citati: ", "; ".join(campi["allegati_citati"]["valore"][:4]) + refs(campi, "allegati_citati")))
    if "sopralluogo" in campi:
        t = str(campi["sopralluogo"]["valore"])
        items.append(("Accesso ai dati e sopralluogo: ", (t if len(t) <= 170 else t[:167].rstrip() + "…") + refs(campi, "sopralluogo")))
    when = (nota if nota and nota.lower().startswith("scadenza") else f"{scad:%d/%m/%Y}" + (f" – {nota}" if nota else "")) if scad else None
    items.append(("Scadenza: ", when or "non trovata – verificare sul documento"))
    missing = [lab for k, lab in (("cig", "CIG"), ("importo_massimo_eur", "importo"), ("durata", "durata"),
                                   ("punti_luce", "punti luce"), ("criterio_aggiudicazione", "criterio")) if k not in campi]
    items.append(("Non trovato nei documenti: ", ", ".join(missing) if missing else "nulla di rilevante"))
    return items[:9]


def economica_rows(campi: dict) -> list[tuple[str, str, str]]:
    """(voce, valore, fonte) for the three rows of "Pre-valutazione economica"."""
    def src(k: str) -> str:
        return (campi[k].get("fonte") or DC) if k in campi else DC

    spesa = (campi.get("spesa_annua_eur") or {}).get("valore")
    cons = (campi.get("consumi_mwh") or {}).get("valore")
    rows = [
        ("Spesa storica (energia, O&M, straordinaria)", f"{_campo('spesa_annua_eur', spesa)}/anno (come scritto nel documento)" if spesa else DC, src("spesa_annua_eur")),
        ("Energia", f"~{it_num(cons, 0 if float(cons).is_integer() else 1)} MWh/anno" if cons else DC, src("consumi_mwh")),
    ]
    canone = (campi.get("canone_annuo_eur") or {}).get("valore")
    if canone:
        rows.append(("Canone annuo di riferimento (base di gara)", f"{_campo('canone_annuo_eur', canone)}/anno", src("canone_annuo_eur")))
    else:
        rows.append(("Manutenzione", DC, DC))
    return rows


def concorrenza_items(campi: dict) -> list[tuple[str, str]]:
    prop = (campi.get("proponente") or {}).get("valore")
    first = ("Proponente: ", (f"{prop['nome']}" + (f", proposta prot. {prop['protocollo']} del {prop['data']}" if prop.get("protocollo") else "") + refs(campi, "proponente")) if prop else DC)
    others = [(f"{lab}: ", DC) for lab in ("Gestore uscente", "Manutentore", "Visibilità dell'avviso", "Prelazione", "Convenzioni Consip", "Leve nostre")]
    return [first, *others]
