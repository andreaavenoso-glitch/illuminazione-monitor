import enum


class StatoProcedurale(str, enum.Enum):
    PRE_GARA = "PRE-GARA"
    GARA_PUBBLICATA = "GARA PUBBLICATA"
    RETTIFICA = "RETTIFICA-PROROGA-CHIARIMENTI"
    ESITO = "ESITO-AGGIUDICAZIONE-VARIANTE-REVOCA"


class TipoNovita(str, enum.Enum):
    NUOVO_OGGI = "Nuovo oggi"
    NUOVO_EMERSO_OGGI = "Nuovo emerso oggi ma pubblicato prima"
    AGGIORNAMENTO = "Aggiornamento gara nota"
    SEGNALE_PRE_GARA = "Segnale pre-gara"


class ValidationLevel(str, enum.Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class ReliabilityIndex(str, enum.Enum):
    ALTA = "Alta"
    MEDIA = "Media"
    BASSA = "Bassa"


class SourcePriority(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"


class PreGaraForza(str, enum.Enum):
    FORTE = "forte"
    DEBOLE = "debole"
