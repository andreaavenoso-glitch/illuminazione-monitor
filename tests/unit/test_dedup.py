from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.deduplication import compute_dedup_key, deduplicate_group


@dataclass
class FakeRecord:
    id: UUID
    cig: str | None
    ente: str
    descrizione: str | None
    importo: Decimal | None
    source_priority_rank: int
    first_seen_at: datetime
    stato_procedurale: str = "GARA PUBBLICATA"


def _record(**overrides) -> FakeRecord:
    base = dict(
        id=uuid4(),
        cig=None,
        ente="Comune di Test",
        descrizione="Illuminazione pubblica",
        importo=Decimal("1000000"),
        source_priority_rank=4,
        first_seen_at=datetime(2026, 4, 22, 10, tzinfo=UTC),
        stato_procedurale="GARA PUBBLICATA",
    )
    base.update(overrides)
    return FakeRecord(**base)


class TestDedupKey:
    def test_cig_wins(self) -> None:
        key = compute_dedup_key(
            cig="ABCDEFGH12",
            ente="Comune A",
            oggetto="qualunque",
            importo=Decimal("1000000"),
        )
        assert key == "cig:ABCDEFGH12"

    def test_fallback_buckets_importo_to_50k(self) -> None:
        a = compute_dedup_key(cig=None, ente="ente", oggetto="ogg", importo=Decimal("1240000"))
        b = compute_dedup_key(cig=None, ente="ente", oggetto="ogg", importo=Decimal("1260000"))
        assert a == "eo:ente|ogg|1250000"
        assert b == "eo:ente|ogg|1250000"

    def test_fallback_truncates_long_strings(self) -> None:
        long_ente = "Comune di Castelfranco Emilia in provincia di Modena Emilia-Romagna"
        key = compute_dedup_key(
            cig=None,
            ente=long_ente,
            oggetto="oggetto molto lungo che deve essere troncato per evitare collisioni minori",
            importo=None,
        )
        assert key.startswith("eo:")
        # ente truncated to 28 chars
        ente_part = key.split("|", 1)[0].removeprefix("eo:")
        assert len(ente_part) == 28

    def test_no_importo_uses_x(self) -> None:
        key = compute_dedup_key(cig=None, ente="ente", oggetto="ogg", importo=None)
        assert key.endswith("|x")


class TestDeduplicateGroup:
    def test_single_record_is_master(self) -> None:
        rec = _record()
        group = deduplicate_group([rec])
        assert group.master_id == str(rec.id)
        assert group.duplicate_ids == []
        assert group.member_count == 1

    def test_lowest_rank_wins(self) -> None:
        master = _record(source_priority_rank=1)
        dup_a = _record(source_priority_rank=4)
        dup_b = _record(source_priority_rank=6)
        group = deduplicate_group([dup_a, dup_b, master])
        assert group.master_id == str(master.id)
        assert set(group.duplicate_ids) == {str(dup_a.id), str(dup_b.id)}
        assert group.member_count == 3

    def test_tie_broken_by_earliest_first_seen(self) -> None:
        early = _record(
            source_priority_rank=2, first_seen_at=datetime(2026, 4, 1, tzinfo=UTC)
        )
        late = _record(source_priority_rank=2, first_seen_at=datetime(2026, 4, 22, tzinfo=UTC))
        group = deduplicate_group([late, early])
        assert group.master_id == str(early.id)

    def test_empty_returns_no_master(self) -> None:
        group = deduplicate_group([])
        assert group.master_id is None

    def test_esito_wins_over_gara_pubblicata_even_with_worse_source_rank(self) -> None:
        # Same CIG, two lifecycle stages: the original bando (from a highly
        # ranked source) and, weeks later, its esito di aggiudicazione (from
        # a lower-ranked source, e.g. ANAC vs. the comune's own portal). The
        # esito must win regardless -- otherwise an awarded tender keeps
        # showing as still open.
        bando = _record(
            source_priority_rank=1,
            stato_procedurale="GARA PUBBLICATA",
            first_seen_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        esito = _record(
            source_priority_rank=5,
            stato_procedurale="ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA",
            first_seen_at=datetime(2026, 4, 15, tzinfo=UTC),
        )
        group = deduplicate_group([bando, esito])
        assert group.master_id == str(esito.id)
        assert group.duplicate_ids == [str(bando.id)]

    def test_rettifica_wins_over_gara_pubblicata(self) -> None:
        bando = _record(source_priority_rank=1, stato_procedurale="GARA PUBBLICATA")
        rettifica = _record(source_priority_rank=5, stato_procedurale="RETTIFICA-PROROGA-CHIARIMENTI")
        group = deduplicate_group([bando, rettifica])
        assert group.master_id == str(rettifica.id)

    def test_pre_gara_never_beats_a_published_gara(self) -> None:
        pre_gara = _record(source_priority_rank=1, stato_procedurale="PRE-GARA")
        gara = _record(source_priority_rank=5, stato_procedurale="GARA PUBBLICATA")
        group = deduplicate_group([pre_gara, gara])
        assert group.master_id == str(gara.id)

    def test_same_stage_still_breaks_ties_by_source_rank(self) -> None:
        # Two records at the same lifecycle stage (e.g. the same bando
        # mirrored on two portals): source reliability still decides.
        best = _record(source_priority_rank=1, stato_procedurale="GARA PUBBLICATA")
        worse = _record(source_priority_rank=4, stato_procedurale="GARA PUBBLICATA")
        group = deduplicate_group([worse, best])
        assert group.master_id == str(best.id)
