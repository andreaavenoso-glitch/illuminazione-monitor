from sector_dictionaries import extract_tags


def test_led_and_relamping() -> None:
    tags = extract_tags("Relamping LED illuminazione pubblica")
    assert "LED" in tags


def test_telegestione() -> None:
    tags = extract_tags("Servizio di telegestione e telecontrollo")
    assert "telegestione" in tags
    assert "telecontrollo" in tags


def test_ppp_and_pnrr() -> None:
    tags = extract_tags("Concessione project financing, finanziamento PNRR React-EU")
    assert "PPP" in tags
    assert "PNRR" in tags


def test_sopra_soglia() -> None:
    tags = extract_tags("gara per illuminazione", importo=6_000_000)
    assert "sopra soglia UE" in tags


def test_below_threshold_no_tag() -> None:
    tags = extract_tags("gara per illuminazione", importo=500_000)
    assert "sopra soglia UE" not in tags


def test_accordo_quadro() -> None:
    tags = extract_tags("Accordo-quadro per manutenzione illuminazione")
    assert "accordo quadro" in tags
    assert "manutenzione" in tags


def test_empty_input() -> None:
    assert extract_tags(None) == []
    assert extract_tags("") == []


def test_semafori_accorpati() -> None:
    tags = extract_tags("Servizio illuminazione e impianti semaforici accorpati")
    assert "semafori accorpati" in tags
