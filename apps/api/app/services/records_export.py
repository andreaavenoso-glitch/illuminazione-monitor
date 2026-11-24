"""CSV export of a region's records, so they can be reviewed and analysed offline."""
from __future__ import annotations

import csv
import io

COLUMNS = [
    "regione", "categoria", "servizi", "ente", "descrizione", "data_pubblicazione",
    "scadenza", "ancora_valido", "stato_verifica", "stato", "atto_tipo", "link", "visto_il",
]


def records_csv(rows: list[dict]) -> str:
    """``rows`` use the COLUMNS keys. UTF-8 text with a BOM so Excel opens accents correctly."""
    out = io.StringIO()
    out.write("﻿")
    w = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore", delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
    return out.getvalue()
