from uuid import uuid4

from app.services.admin_service import pacchetto_steps
from shared_models.lavorazione import STATI


def test_the_package_reads_the_documents_first_then_looks_for_the_referenti():
    rid = uuid4()
    steps = pacchetto_steps(rid, "approfondita")
    assert [n for n, _ in steps] == [
        "app.tasks.analyze_record.analyze_record",
        "app.tasks.find_referenti.find_referenti",
    ]
    assert steps[0][1] == {"record_id": str(rid), "profondita": "approfondita"}
    assert steps[1][1] == {"record_id": str(rid)}


def test_the_two_decisions():
    assert STATI == ("selezionata", "scartata")
