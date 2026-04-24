from datetime import UTC, datetime, timedelta

from app.domain.classification import classify_stato_procedurale, classify_tipo_novita


class TestClassifyStato:
    def test_esito_keywords(self) -> None:
        assert classify_stato_procedurale(
            descrizione="Aggiudicazione definitiva gara illuminazione pubblica",
            raw_body=None,
            cig=None,
            link="https://x",
        ) == "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA"

    def test_rettifica_keywords(self) -> None:
        assert classify_stato_procedurale(
            descrizione="Proroga termini scadenza",
            raw_body="rettifica dei documenti di gara",
            cig="ABCDEFGH12",
            link="https://x",
        ) == "RETTIFICA-PROROGA-CHIARIMENTI"

    def test_pre_gara_from_delibera(self) -> None:
        assert classify_stato_procedurale(
            descrizione="Delibera Giunta n. 12 illuminazione pubblica",
            raw_body=None,
            cig=None,
            link="https://x",
        ) == "PRE-GARA"

    def test_pre_gara_from_atto_tipo(self) -> None:
        assert classify_stato_procedurale(
            descrizione="oggetto generico",
            raw_body=None,
            cig=None,
            link="https://x",
            atto_tipo="determina",
        ) == "PRE-GARA"

    def test_notizia_atto_not_forced_to_pre_gara(self) -> None:
        # When atto_tipo is "notizia" the override doesn't apply.
        result = classify_stato_procedurale(
            descrizione="Aggiudicazione definitiva",
            raw_body=None,
            cig=None,
            link="https://x",
            atto_tipo="notizia",
        )
        assert result == "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA"

    def test_gara_pubblicata_default(self) -> None:
        assert classify_stato_procedurale(
            descrizione="Procedura aperta illuminazione pubblica",
            raw_body=None,
            cig="ABCDEFGH12",
            link="https://x",
        ) == "GARA PUBBLICATA"


class TestClassifyTipoNovita:
    def test_segnale_pre_gara(self) -> None:
        now = datetime(2026, 4, 22, tzinfo=UTC)
        assert (
            classify_tipo_novita(
                first_seen_at=now,
                data_pubblicazione=now,
                is_existing_record=False,
                stato_procedurale="PRE-GARA",
                now=now,
            )
            == "Segnale pre-gara"
        )

    def test_nuovo_oggi(self) -> None:
        now = datetime(2026, 4, 22, 10, tzinfo=UTC)
        assert (
            classify_tipo_novita(
                first_seen_at=now,
                data_pubblicazione=now,
                is_existing_record=False,
                stato_procedurale="GARA PUBBLICATA",
                now=now,
            )
            == "Nuovo oggi"
        )

    def test_nuovo_emerso_oggi_ma_pubblicato_prima(self) -> None:
        now = datetime(2026, 4, 22, 10, tzinfo=UTC)
        pub_before = now - timedelta(days=10)
        assert (
            classify_tipo_novita(
                first_seen_at=now,
                data_pubblicazione=pub_before,
                is_existing_record=False,
                stato_procedurale="GARA PUBBLICATA",
                now=now,
            )
            == "Nuovo emerso oggi ma pubblicato prima"
        )

    def test_aggiornamento_gara_nota(self) -> None:
        now = datetime(2026, 4, 22, 10, tzinfo=UTC)
        first_seen = now - timedelta(days=7)
        assert (
            classify_tipo_novita(
                first_seen_at=first_seen,
                data_pubblicazione=first_seen,
                is_existing_record=True,
                stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI",
                now=now,
            )
            == "Aggiornamento gara nota"
        )
