import io
import json
import zipfile
from datetime import date

from app.collectors.census import census_stats, census_text
from app.collectors.doc_fields import extract_fields, split_members
from app.services.gate_content import (
    DC,
    censimento_items,
    concorrenza_items,
    desiderata_items,
    economica_rows,
    informazioni_items,
    procedura_text,
    refs,
)
from app.services.gate_deck import NO_MODEL, find_gate_template
from pptx import Presentation

TODAY = date(2026, 11, 23)


def _pdf_text(*pages: str) -> str:
    return "\f".join(pages)


AVVISO = _pdf_text(
    "CITTA' DI SCANZANO JONICO Avviso pubblico per la presentazione di proposte di finanza di progetto. "
    "originata dalla proposta della società CiviSmart S.p.A ., prot. n. 0009975 del 22/05/2025, con la deliberazione della Giunta comunale n. 85 del 06/08/2025.",
    "La durata di riferimento della concessione è di 20 anni. Il canone annuo di riferimento da porre a base della gara è pari a € 230.000,00, oltre IVA.",
    "Le proposte devono pervenire entro le ore 12:00 del 20-01-2027 via PEC a protocollo@pec.comune.x.it. "
    "La scadenza ufficialmente indicata per la domanda regionale è 15/02/2027, ore 12:00. "
    "PR Basilicata FESR FSE+ 2021 –2027, Priorità 3, obiettivo RSO 2.1, Azione 3.2.1.B.",
)


def test_every_field_names_its_document_and_its_page():
    f = extract_fields([("avviso.pdf", AVVISO)], TODAY)
    assert f["proponente"]["fonte"] == "avviso.pdf, p. 1"
    assert f["proponente"]["valore"] == {"nome": "CiviSmart S.p.A.", "protocollo": "0009975", "data": "22/05/2025"}
    assert f["durata"]["fonte"] == "avviso.pdf, p. 2" and f["canone_annuo_eur"]["fonte"] == "avviso.pdf, p. 2"
    assert f["scadenza"]["fonte"] == "avviso.pdf, p. 3" and f["scadenza"]["valore"] == "2027-01-20"
    assert f["finanziamento"]["valore"] == "PR Basilicata FESR FSE+ 2021–2027, Azione 3.2.1.B"
    assert f["scadenza_finanziamento"]["valore"] == "2027-02-15 12:00"


def test_a_single_page_document_has_no_page_number():
    f = extract_fields([("avviso.html", "Il canone annuo è pari a € 12.000,00 oltre IVA, " + "testo " * 20)], TODAY)
    assert f["canone_annuo_eur"]["fonte"] == "avviso.html"


def test_the_files_of_an_archive_are_separate_documents():
    text = "[Archivio con 2 file letti: a.pdf, b.txt] [a.pdf] La durata è di 15 anni. [b.txt] Il canone annuo è di € 50.000,00."
    assert [m for m, _ in split_members(text)] == [None, "a.pdf", "b.txt"]
    f = extract_fields([("allegati.zip", text)], TODAY)
    assert f["durata"]["fonte"] == "allegati.zip › a.pdf" and f["canone_annuo_eur"]["fonte"] == "allegati.zip › b.txt"


def _census_xlsx() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "centri luminosi"
    ws.append(["centro luminoso", "corpo illuminante", "C.L.", "QUADRO", "UBICAZIONE", "TIPO APPARECCHIO", "STATO APPARECCHIO", "TIPO SORGENTE ",
               "POTENZA SORGENTE\n (W)", "POTENZA SORGENTE\n+\nALIMETATORE (W)", "TIPO DI INSTALLAZIONE", "TIPO SOSTEGNO", "ALTEZZA SOSTEGNO",
               "MATERIALE SOSTEGNO", "STATO SOSTEGNO", "x", "x", "TIPO LINEA", "x", "x", "x", "x", "x", "x", "x", "x", "TIPOLOGIA DELL'AMBITO"])
    ws.append(["Da nascondere"] + [None] * 26)
    for i in range(10):
        ws.append([100 + i // 2, 200 + i, f"AA{i:03d}", "AA", "Via X", "Armatura Stradale", "Da sostituire" if i % 2 else "Da revisionare",
                   "LED" if i < 4 else "SAP", 50, 60, "Testa palo", "Palo conico", 7, "ferro zincato", "Adeguato", None, None, "Cavo interrato",
                   None, None, None, None, None, None, None, None, "Veicolare"])
    q = wb.create_sheet("quadri")
    q.append(["ID QUADRO", "NUMERO PROGRESSIVO", "INDIRIZZO", "ORE ANNUE ACCENSIONE"])
    q.append(["1", 1, "Via X", 4000])
    q.append(["2", 2, "Via Y", 4000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_the_census_is_read_by_column():
    c = census_stats(_census_xlsx())
    assert c["apparecchi"] == 10 and c["centri_luminosi"] == 5 and c["quadri"] == 2  # the template's sample row is left out
    assert c["sorgenti"] == {"SAP": 6, "LED": 4}
    assert c["potenza_kw"] == 0.6 and c["ore_annue"] == 4000 and c["consumo_mwh"] == 2  # 600 W x 4000 h
    assert c["stato_apparecchio"] == {"Da revisionare": 5, "Da sostituire": 5}
    assert census_stats(b"not a workbook") is None


def test_a_census_inside_an_archive_becomes_fields_with_its_source():
    text = "[Archivio con 1 file letti: Scheda.xlsx] [Scheda.xlsx] " + census_text(census_stats(_census_xlsx()))
    f = extract_fields([("allegati tecnici.zip", text)], TODAY)
    assert f["censimento"]["valore"]["apparecchi"] == 10
    assert f["punti_luce"]["valore"] == "10" and f["punti_luce"]["fonte"] == "allegati tecnici.zip › Scheda.xlsx"
    assert f["consumi_mwh"]["valore"] == 2.0


def test_the_texts_of_the_sheet_carry_their_references():
    f = extract_fields([("avviso.pdf", AVVISO)], TODAY)
    assert refs(f, "scadenza", "ora_scadenza", "pec_invio") == " [fonte: avviso.pdf (p. 3)]"
    assert refs(f, "durata", "proponente") == " [fonte: avviso.pdf (p. 1, 2)]"
    assert refs(f, "inesistente") == ""
    t = procedura_text(f, "Manifestazione di interesse")
    assert "art. 193" in t and "CiviSmart S.p.A. (prot. 0009975 del 22/05/2025)" in t and "[fonte: avviso.pdf (p. 1)]" in t
    rows = economica_rows(f)
    assert rows[2][0].startswith("Canone annuo") and "230.000" in rows[2][1] and rows[2][2] == "avviso.pdf, p. 2" and rows[0][1] == DC
    assert concorrenza_items(f)[0][1].startswith("CiviSmart S.p.A., proposta prot. 0009975")
    assert concorrenza_items({})[0][1] == DC


def test_the_census_fills_the_consistency_lines_and_the_rest_stays_to_fill_in():
    c = census_stats(_census_xlsx())
    f = {"censimento": {"valore": c, "fonte": "zip › Scheda.xlsx"}, "durata": {"valore": "20 anni", "fonte": "avviso.pdf, p. 2"}}
    lines = dict(desiderata_items(f))
    assert lines["Consistenza: "].startswith("10 apparecchi su 5 centri luminosi, 2 quadri [fonte: Scheda.xlsx]")
    assert "LED 40% (4)" in lines["Sorgenti: "] and "~2 MWh/anno" in lines["Consumi: "]
    assert lines["Concessione: "].startswith("20 anni") and lines["Centro storico e vincoli: "] == DC and lines["Servizi smart: "] == DC
    assert len(desiderata_items(f)) <= 14
    assert censimento_items(c, "")[0][0] == "Consistenza: "


def test_the_information_slide_lists_the_documents_the_acts_and_the_deadline_once():
    f = extract_fields([("avviso.pdf", AVVISO)], TODAY)
    items = informazioni_items(f, "Manifestazione di interesse", "https://c.it/a", [{"nome": "avviso.pdf", "url": "https://c.it/a.pdf"}],
                               date(2027, 1, 20), "Scadenza 20/01/2027 ore 12:00 letta in avviso.pdf")
    d = dict(items)
    assert d["Scadenza: "] == "Scadenza 20/01/2027 ore 12:00 letta in avviso.pdf" and "Atti richiamati: " in d


def _pptx(path, *titles):
    prs = Presentation()
    for t in titles:
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = t
    prs.save(path)


def test_the_a2a_model_is_found_or_the_error_says_what_to_do(tmp_path):
    other = tmp_path / "altro.pptx"
    model = tmp_path / "Gate_1.pptx"
    _pptx(other, "Presentazione qualunque")
    _pptx(model, "1| Dati generali PF", "3| Pianificazione gate (1 di 1)")
    assert find_gate_template(None, (str(tmp_path),)) == str(model)  # found in the folder, whatever its name
    assert find_gate_template(str(model), ()) == str(model)  # configured
    assert find_gate_template(str(other), ()) is None  # a file that is not the A2A sheet is not used
    assert find_gate_template("/non/esiste.pptx", ()) is None
    assert "infra/modelli" in NO_MODEL and "PPT_TEMPLATE_PATH" in NO_MODEL


def test_json_marker_roundtrip():
    c = census_stats(_census_xlsx())
    assert json.loads(census_text(c).split("[[CENSIMENTO ", 1)[1].split("]]", 1)[0])["apparecchi"] == 10
    assert zipfile.is_zipfile(io.BytesIO(_census_xlsx()))


def test_the_model_is_found_wherever_it_was_dropped_under_infra(tmp_path):
    infra = tmp_path / "infra"
    deep = infra / "prove" / "modello"
    deep.mkdir(parents=True)
    _pptx(deep / "Gate_1_Bovezzo_(BS).pptx", "1| Dati generali PF", "3| Pianificazione gate (1 di 1)")
    assert find_gate_template(None, (str(infra),)) == str(deep / "Gate_1_Bovezzo_(BS).pptx")
    # a file in a "modelli" folder wins over one left elsewhere
    good = infra / "modelli"
    good.mkdir()
    _pptx(good / "gate1.pptx", "1| Dati generali PF", "3| Pianificazione gate (1 di 1)")
    assert find_gate_template(None, (str(infra),)) == str(good / "gate1.pptx")
    # the sheets this app generates are not mistaken for the model
    gen = infra / "prove" / "scheda_Comune_x.pptx"
    _pptx(gen, "In sintesi", "Referenti")
    assert find_gate_template(None, (str(tmp_path / "vuoto"),)) is None
