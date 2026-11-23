import io
import zipfile

from app.collectors.archives import Limits, archive_to_text, bytes_to_text, docx_to_text, sniff, xlsx_to_text
from app.collectors.deadline_hunt import doc_links
from app.tasks.verify_records import attachment_links


def _zip(files: dict[str, bytes], **kw) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _docx(text: str) -> bytes:
    xml = f'<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:p><w:r><w:t>seconda riga &amp; fine</w:t></w:r></w:p></w:body></w:document>'
    return _zip({"word/document.xml": xml.encode(), "[Content_Types].xml": b"<x/>"})


def _xlsx(*cells: str) -> bytes:
    sst = "<sst>" + "".join(f"<si><t>{c}</t></si>" for c in cells) + "</sst>"
    return _zip({"xl/workbook.xml": b"<x/>", "xl/sharedStrings.xml": sst.encode()})


def fake_pdf(data: bytes) -> str:
    return "testo del pdf" if data.startswith(b"%PDF") and b"scan" not in data else ""


def test_sniff_tells_the_formats_from_the_first_bytes():
    assert sniff(b"%PDF-1.7 ...") == "pdf"
    assert sniff(_docx("x")) == "docx" and sniff(_xlsx("a")) == "xlsx"
    assert sniff(_zip({"a.txt": b"x"})) == "zip"
    assert sniff(b"<html>", "text/html", "https://c.it/p") == "other"
    assert sniff(b"junk", "application/pdf", "https://c.it/a") == "pdf"  # header says pdf


def test_word_and_excel_text():
    assert docx_to_text(_docx("Importo € 100.000")) == "Importo € 100.000 seconda riga & fine"
    assert xlsx_to_text(_xlsx("Quadro economico", "Punti luce 1057")) == "Quadro economico Punti luce 1057"
    assert docx_to_text(b"not a zip") == ""


def test_archive_reads_pdfs_word_text_and_says_where_each_text_comes_from():
    z = _zip({"relazione.pdf": b"%PDF-1.4 x", "capitolato.docx": _docx("Durata 15 anni"), "dati.txt": b"consumi 170 MWh"})
    text, read, notes = archive_to_text(z, fake_pdf)
    assert read == ["relazione.pdf", "capitolato.docx", "dati.txt"] and notes == []
    assert "[relazione.pdf] testo del pdf" in text and "[capitolato.docx] Durata 15 anni" in text and "consumi 170 MWh" in text


def test_archive_is_defensive():
    z = _zip({
        "../evil.txt": b"fuori", "/abs.txt": b"fuori", "ok.txt": b"dentro", "scan.pdf": b"%PDF scan",
        "foto.jpg": b"\xff\xd8", "grande.txt": b"x" * 5000,
    })
    text, read, notes = archive_to_text(z, fake_pdf, Limits(max_member_bytes=1000))
    assert read == ["ok.txt"] and "dentro" in text and "fuori" not in text
    why = " | ".join(notes)
    assert "evil.txt" in why and "abs.txt" in why and "scansione" in why and "non supportato" in why and "troppo grande" in why


def test_archive_limits_on_count_and_ratio_and_nesting():
    many = _zip({f"f{i}.txt": b"a" for i in range(10)})
    _, read, notes = archive_to_text(many, fake_pdf, Limits(max_members=3))
    assert len(read) == 3 and any("primi 3" in n for n in notes)
    bomb = _zip({"bomba.txt": b"0" * 200_000})
    text, read, notes = archive_to_text(bomb, fake_pdf, Limits(max_ratio=50))
    assert read == [] and any("compressione sospetto" in n for n in notes)
    inner = _zip({"b.txt": b"interno"})
    outer = _zip({"a.zip": inner, "c.txt": b"esterno"})
    text, read, _ = archive_to_text(outer, fake_pdf)
    assert "a.zip/b.txt" in read and "interno" in text and "esterno" in text
    deep = _zip({"x.zip": _zip({"y.zip": _zip({"z.txt": b"troppo"})})})
    text, read, notes = archive_to_text(deep, fake_pdf)
    assert "troppo" not in text and any("dentro un archivio" in n for n in notes)


def test_bytes_to_text_for_a_zip_names_the_files_and_explains_an_empty_one():
    kind, text, note = bytes_to_text(_zip({"relazione.pdf": b"%PDF-1.4"}), "application/zip", "https://c.it/allegati.zip", fake_pdf)
    assert kind == "zip" and text.startswith("[Archivio con 1 file letti: relazione.pdf]") and note == ""
    kind, text, note = bytes_to_text(_zip({"foto.jpg": b"x"}), "", "https://c.it/a.zip", fake_pdf)
    assert kind == "zip" and text == "" and "non supportato" in note
    assert bytes_to_text(b"<html>pagina</html>", "text/html", "https://c.it/p", fake_pdf) == ("", "", "")


HTML = (
    '<html><body><a href="/allegati/tecnici.zip">Allegati tecnici</a><a href="/doc/capitolato.docx">Capitolato</a>'
    '<a href="/img/logo.jpg">logo</a><a href="/doc/vecchio.doc">Documento vecchio</a></body></html>'
)


def test_archives_and_word_are_now_followed_as_documents():
    links = [u for _, u in doc_links(HTML, "https://c.it/avviso/", seen=set())]
    assert "https://c.it/allegati/tecnici.zip" in links and "https://c.it/doc/capitolato.docx" in links
    assert not any(u.endswith((".jpg", ".doc")) for u in links)
    att = attachment_links(HTML, base_url="https://c.it/avviso/", limit=8)
    assert "https://c.it/allegati/tecnici.zip" in att and not any(u.endswith(".jpg") for u in att)


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_zip_attachment_of_a_notice_is_downloaded_and_read(httpx_mock):
    from app.collectors.doc_collect import LIVELLI, collect_docs
    from app.tasks.verify_records import _fetch_plain

    page = (
        "<html><body>" + "<p>Avviso pubblico per il servizio di illuminazione pubblica.</p>" * 80
        + '<a href="/allegati/tecnici.zip">Allegati tecnici</a></body></html>'
    )
    z = _zip({"capitolato.docx": _docx("Durata 15 anni. Importo € 1.075.000,00"), "dati.txt": b"consumi 170 MWh/anno"})
    httpx_mock.add_response(url="https://c.it/avviso/", text=page, headers={"content-type": "text/html"})
    httpx_mock.add_response(url="https://c.it/allegati/tecnici.zip", content=z, headers={"content-type": "application/zip"})
    docs, _ = await collect_docs("https://c.it/avviso/", _fetch_plain, LIVELLI["base"])
    names = [d.name for d in docs]
    assert names == ["pagina dell'avviso", "tecnici.zip"]
    zip_text = docs[1].text
    assert zip_text.startswith("[Archivio con 2 file letti: capitolato.docx, dati.txt]")
    assert "Durata 15 anni" in zip_text and "170 MWh/anno" in zip_text
