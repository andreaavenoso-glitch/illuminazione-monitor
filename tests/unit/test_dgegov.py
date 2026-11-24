"""The dgegovpa.it portal (albo and bandi di gara pages), with the markup of a real page of a comune."""
from app.collectors.dgegov import cig_url, clean_url
from app.collectors.page_gate import gate_page

BASE = "https://dgegovpa.it/Arluno/albo/albo.aspx?tipologia=DETERMINAZIONE"


def _albo_item(n: int, num: int, title: str, pdf: str, extra: str = "") -> str:
    return f"""<div class="row"><div class="col-lg-2"><div class="card-body row">
<span class="h5 mb-0"><div id="ctl00_ContentPlaceHolder1_RepAffissioniAlbo_RptAlbo_ctl{n:02d}_divFirst" class="text-value">N. <b>{num}</b></div></span>
<span class="h5 mb-0"><div id="ctl00_ContentPlaceHolder1_RepAffissioniAlbo_RptAlbo_ctl{n:02d}_divSecond">pubblicata il</div></span>
<span class="h5 mb-0"><div id="ctl00_ContentPlaceHolder1_RepAffissioniAlbo_RptAlbo_ctl{n:02d}_divThird" class="text-uppercase"><b>19/11/2026</b></div></span>
</div></div><div class="col-lg-10"><span class="h5">{title}</span>
<div class="collapse-body"><ul class="list-unstyled mb-0">
<li><span>Fine pubblicazione:</span><b>04/12/2026</b></li><li><span>Tipo documento:</span> <strong> Determinazione </strong></li>
<li><span>Settore:</span> <strong>AREA LL.PP. ECOLOGIA</strong></li>
<li>Scarica il documento: <a target="_blank" class="pdf" href="{pdf}">{pdf.rsplit('/', 1)[-1]}<span> ( 75,13 Kb )</span></a></li></ul></div></div></div><hr />{extra}"""


def _bandi_row(n: int, date: str, cig: str, title: str) -> str:
    return f"""<tr id="ctl00_ContentPlaceHolder1_RepBandi_ctl{n:02d}_TrBando" onclick="javascript:__doPostBack('x','')">
<td class="align-top text-center"><span title="Data di pubblicazione">{date}</span></td>
<td class="align-top"><strong title="Codice identificativo gara">{cig}</strong></td>
<td class="align-top" title="Oggetto"> {title} </td>
<td><input type="submit" name="ctl00$ContentPlaceHolder1$RepBandi$ctl{n:02d}$BtnDett" value="Dettaglio" /></td></tr>"""


FILTERS = '<select><option>FINANZA DI PROGETTO</option><option>CONCESSIONI E PARTENARIATO PUBBLICO PRIVATO</option></select>'


def test_albo_item_with_the_title_apart_from_its_pdf_becomes_a_candidate():
    html = "<html><body>" + FILTERS + _albo_item(0, 1207, "AFFIDAMENTO DEL SERVIZIO DI GESTIONE DELLA PUBBLICA ILLUMINAZIONE", "/Arluno/albo/dati/20260759D.PDF") \
        + _albo_item(1, 1206, "MODIFICA ORARIO DI LAVORO DIPENDENTE", "/Arluno/albo/dati/20260758D.PDF") + "</body></html>"
    g = gate_page(html, base_url=BASE + "&_mpag=2")
    assert g.action == "compact" and g.template == "dgegov"
    assert len(g.candidates) == 1  # the other act is not about a service
    c = g.candidates[0]
    assert "PUBBLICA ILLUMINAZIONE" in c.title and c.date == "19/11/2026"
    assert c.href == "https://dgegovpa.it/Arluno/albo/dati/20260759D.PDF"  # the act's own document


def test_bandi_rows_carry_the_cig_in_their_address():
    html = ('<html><body>' + FILTERS + '<table id="tblbandi"><tbody>'
            + _bandi_row(1, "18/11/2026", "BDD69F718E", "ATTIVAZIONE FORNITURA DI GAS NATURALE SEDE PROTEZIONE CIVILE")
            + _bandi_row(2, "17/11/2026", "BD8029248D", "PROCEDURA DI ESTERNALIZZAZIONE DEL SERVIZIO DI PUBBLICA ILLUMINAZIONE")
            + '</tbody></table></body></html>')
    g = gate_page(html, base_url="https://dgegovpa.it/Arluno/Trasparenza/bandigaracontratti2.aspx?_mpag=3")
    assert [c.href for c in g.candidates] == ["https://dgegovpa.it/Arluno/Trasparenza/bandigaracontratti2.aspx?cig=BD8029248D"]
    assert "BD8029248D" in g.candidates[0].snippet


def test_a_portal_page_with_nothing_of_interest_never_goes_to_claude():
    """The portal's filter lists name "finanza di progetto" on every page: that is not an entry."""
    html = "<html><body>" + FILTERS + _albo_item(0, 1, "MODIFICA ORARIO DI LAVORO", "/a.PDF") + "</body></html>"
    assert gate_page(html, base_url=BASE).action == "skip"


def test_urls_without_the_page_marker():
    assert clean_url(BASE + "&_mpag=4#x") == BASE
    assert cig_url("https://dgegovpa.it/A/b.aspx?_mpag=2", "BD8029248D") == "https://dgegovpa.it/A/b.aspx?cig=BD8029248D"


def test_list_page_is_not_read_as_the_detail_of_its_own_entries():
    from app.tasks.collect_watchlist import _same_page

    assert _same_page("https://x.it/b.aspx?cig=1&_mpag=2#c", "https://x.it/b.aspx?cig=1")
    assert not _same_page("https://x.it/dati/a.PDF", "https://x.it/b.aspx")
