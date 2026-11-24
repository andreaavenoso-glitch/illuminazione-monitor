from datetime import date

from app.collectors.doc_fields import extract_fields
from shared_models.pregara import pregara_label, pregara_tipi


def test_each_signal_is_recognised_from_the_wording():
    assert pregara_tipi("Delibera di Giunta: atto di indirizzo per la riqualificazione") == ["delibera"]
    assert "impegno_spesa" in pregara_tipi("Determina a contrarre e impegno di spesa per il servizio")
    assert "mandato_verificatore" in pregara_tipi("Affidamento dell'incarico di verifica del PFTE al verificatore")
    assert "consulenza" in pregara_tipi("Individuazione della società di consulenza per il supporto al RUP")
    assert "manutenzione" in pregara_tipi("Servizio di manutenzione degli impianti di illuminazione pubblica")


def test_a_notice_can_carry_several_signals_and_none_is_empty():
    t = pregara_tipi("Delibera di Giunta con impegno di spesa per la manutenzione degli impianti")
    assert t == ["delibera", "impegno_spesa", "manutenzione"]
    assert pregara_tipi("Orari di apertura del cimitero") == []
    assert pregara_tipi(None) == []
    assert pregara_label(t) == "Delibera, Impegno di spesa, Manutenzione degli impianti"


def test_delibera_fields_are_read_from_the_document():
    text = (
        "Con deliberazione di Giunta Comunale n. 115 del 02/09/2026 si approva l'atto di indirizzo. "
        "Si assume l'impegno di spesa di € 24.400,00 IVA inclusa. "
        "L'incarico è affidato alla società Verifica Tecnica S.r.l. per la verifica del progetto."
    )
    f = extract_fields([("delibera.pdf", text)], date(2026, 11, 23))
    assert f["atto_estremi"]["valore"] == "Delibera di Giunta n. 115 del 02/09/2026"
    assert f["impegno_spesa_eur"]["valore"] == 24400.0
    assert f["incaricato"]["valore"].startswith("Verifica Tecnica") and f["incaricato"]["valore"].endswith("S.r.l.")


def test_determina_with_year_and_no_company_gives_no_incaricato():
    f = extract_fields([("d.pdf", "Determinazione dirigenziale n. 422/2026 del 19/11/2026 per lavori vari.")], date(2026, 11, 23))
    assert f["atto_estremi"]["valore"] == "Determina n. 422/2026 del 19/11/2026"
    assert "incaricato" not in f


def test_impegno_di_spesa_is_noise_alone_but_a_signal_with_a_process_context():
    from shared_models.categories import categorize, is_noise

    assert is_noise("Determina di impegno di spesa per il pagamento del canone mensile")  # still the payment of a contract
    assert is_noise("Impegno di spesa illuminazione pubblica")  # alone: as before
    assert is_noise("Liquidazione fattura e impegno di spesa per la manutenzione")  # liquidazione stays excluded
    for text in (
        "Impegno di spesa per il mandato al verificatore del PFTE",
        "Delibera di Giunta: impegno di spesa per l'incarico alla società di consulenza (advisor) per illuminazione pubblica",
        "Determina di impegno di spesa per la manutenzione degli impianti di illuminazione pubblica",
    ):
        assert not is_noise(text), text
        assert categorize(stato_procedurale=None, text=text) == "pre_gara"
