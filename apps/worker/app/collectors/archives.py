"""Text from the documents a comune attaches that are not a plain PDF or web page: ZIP archives ("Allegati tecnici"
are very often a .zip with the PDFs inside), Word (.docx) and Excel (.xlsx).

Free and offline. The archives come from the open web, so everything is bounded: number of files, size of each
file and of the whole archive, compression ratio (zip bombs), no path traversal (nothing is ever written to disk:
members are read in memory), no encrypted members, one level of nested archive. The XML of Word and Excel is read
with plain regular expressions, never with an XML parser (no entity expansion tricks).
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

PdfReader = Callable[[bytes], str]


@dataclass(frozen=True)
class Limits:
    max_members: int = 40
    max_member_bytes: int = 30 * 1024 * 1024
    max_total_bytes: int = 120 * 1024 * 1024
    max_ratio: int = 200  # uncompressed / compressed, per member
    max_pdfs: int = 15
    max_chars: int = 400_000


DEFAULT = Limits()
_TEXT_EXT = (".txt", ".csv", ".htm", ".html", ".xml", ".md")
_W_T = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)
_W_P_END = re.compile(r"</w:p>|<w:br\s*/>|<w:tab\s*/>")
_S_T = re.compile(r"<t(?:\s[^>]*)?>(.*?)</t>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")


def sniff(content: bytes, content_type: str = "", url: str = "") -> str:
    """pdf | zip | docx | xlsx | other, from the first bytes (the extension and the header can lie)."""
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:4] == b"PK\x03\x04":
        try:
            names = set(zipfile.ZipFile(io.BytesIO(content)).namelist())
        except (zipfile.BadZipFile, OSError):
            return "other"
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        return "zip"
    low = url.lower().split("?")[0]
    if "pdf" in content_type.lower() or low.endswith(".pdf"):
        return "pdf"
    return "other"


def _clean(s: str) -> str:
    return " ".join(html.unescape(s).split())


def docx_to_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > DEFAULT.max_member_bytes:
                return ""
            xml = z.open(info).read(DEFAULT.max_member_bytes + 1).decode("utf-8", "ignore")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""
    xml = _W_P_END.sub("\n", xml)
    out = []
    for chunk in xml.split("\n"):
        text = "".join(_W_T.findall(chunk))
        if text.strip():
            out.append(_clean(text))
    return " ".join(out)


def xlsx_to_text(content: bytes) -> str:
    """The text cells of a workbook (shared strings): enough to read a quadro economico or a list of plants."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            info = z.getinfo("xl/sharedStrings.xml")
            if info.file_size > DEFAULT.max_member_bytes:
                return ""
            xml = z.open(info).read(DEFAULT.max_member_bytes + 1).decode("utf-8", "ignore")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""
    return " ".join(filter(None, (_clean(_TAG.sub("", m)) for m in _S_T.findall(xml))))


def _safe_name(name: str) -> bool:
    return bool(name) and not name.startswith(("/", "\\")) and ".." not in name.replace("\\", "/").split("/") and ":" not in name[:3]


def archive_to_text(
    content: bytes, pdf_reader: PdfReader, limits: Limits = DEFAULT, _level: int = 0
) -> tuple[str, list[str], list[str]]:
    """(text, files read, notes). Each member's text is introduced by its name so a field can say where it came from.
    ``notes`` lists what was left out and why (scan without text, too big, encrypted, unsupported)."""
    parts: list[str] = []
    read: list[str] = []
    notes: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, OSError):
        return "", [], ["archivio non valido"]
    total = pdfs = 0
    members = [i for i in zf.infolist() if not i.is_dir()]
    if len(members) > limits.max_members:
        notes.append(f"{len(members)} file nell'archivio: letti solo i primi {limits.max_members}")
    for info in members[: limits.max_members]:
        name = info.filename
        if not _safe_name(name):
            notes.append(f"{name}: percorso non valido, saltato")
            continue
        if info.flag_bits & 0x1:
            notes.append(f"{name}: protetto da password")
            continue
        if info.file_size > limits.max_member_bytes or total + info.file_size > limits.max_total_bytes:
            notes.append(f"{name}: troppo grande, saltato")
            continue
        if info.compress_size and info.file_size / max(info.compress_size, 1) > limits.max_ratio:
            notes.append(f"{name}: rapporto di compressione sospetto, saltato")
            continue
        try:
            data = zf.open(info).read(limits.max_member_bytes + 1)  # bounded even if the header lies
        except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError):
            notes.append(f"{name}: non leggibile")
            continue
        if len(data) > limits.max_member_bytes:
            notes.append(f"{name}: troppo grande, saltato")
            continue
        total += len(data)
        low = name.lower()
        text = ""
        kind = sniff(data, "", low)
        if kind == "pdf":
            if pdfs >= limits.max_pdfs:
                notes.append(f"{name}: oltre il limite di {limits.max_pdfs} PDF, saltato")
                continue
            pdfs += 1
            text = pdf_reader(data)
            if not text:
                notes.append(f"{name}: PDF senza testo (scansione) o protetto")
        elif kind == "docx":
            text = docx_to_text(data)
        elif kind == "xlsx":
            text = xlsx_to_text(data)
        elif kind == "zip":
            if _level >= 1:
                notes.append(f"{name}: archivio dentro un archivio, saltato")
            else:
                text, inner, inner_notes = archive_to_text(data, pdf_reader, limits, _level + 1)
                read += [f"{name}/{n}" for n in inner]
                notes += [f"{name}/{n}" for n in inner_notes]
                if text:
                    parts.append(text)
                continue
        elif low.endswith(_TEXT_EXT):
            text = _clean(_TAG.sub(" ", data.decode("utf-8", "ignore")))
        else:
            notes.append(f"{name}: formato non supportato")
            continue
        if text:
            read.append(name)
            parts.append(f"[{name}] {text}")
    return " ".join(parts)[: limits.max_chars], read, notes


def bytes_to_text(content: bytes, content_type: str, url: str, pdf_reader: PdfReader) -> tuple[str, str, str]:
    """(kind, text, note) of a downloaded document that is not a web page. kind is "" when it is not one of the
    supported formats (the caller treats it as a web page)."""
    kind = sniff(content, content_type, url)
    if kind == "pdf":
        text = pdf_reader(content)
        return "pdf", text, "" if text else "PDF senza testo (scansione) o protetto"
    if kind == "docx":
        text = docx_to_text(content)
        return "docx", text, "" if text else "documento Word vuoto"
    if kind == "xlsx":
        text = xlsx_to_text(content)
        return "xlsx", text, "" if text else "foglio Excel senza testo"
    if kind == "zip":
        text, read, notes = archive_to_text(content, pdf_reader)
        head = f"[Archivio con {len(read)} file letti: {', '.join(read[:12])}] " if read else ""
        why = "; ".join(notes[:4])
        return "zip", (head + text) if text else "", "" if text else (why or "archivio senza documenti leggibili")
    return "", "", ""
