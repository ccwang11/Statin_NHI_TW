from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FHScreeningData:
    """Manual evidence for the Taiwan FH diagnostic criteria."""

    first_degree_early_vascular_or_high_ldl: bool = False
    first_degree_xanthoma_or_child_high_ldl: bool = False
    personal_early_cad: bool = False
    personal_early_cerebral_or_pad: bool = False
    xanthoma: bool = False
    corneal_arcus_under_45: bool = False
    functional_gene_mutation: bool = False


@dataclass(frozen=True)
class FHScreeningResult:
    classification: str
    points: int

    @property
    def popup_text(self) -> str:
        return f"{self.classification} ({self.points} points)"

    @property
    def output_text(self) -> str:
        return f"TW FH dx criteria: {self.popup_text}"


def _ldl_points(ldl_c: float | None) -> int:
    if ldl_c is None:
        return 0
    if ldl_c >= 330:
        return 8
    if ldl_c >= 250:
        return 5
    if ldl_c >= 190:
        return 3
    if ldl_c >= 155:
        return 1
    return 0


def evaluate_fh_screening(data: FHScreeningData, ldl_c: float | None) -> FHScreeningResult:
    """Score the Taiwan FH diagnostic criteria shown in the approved screening form."""
    points = _ldl_points(ldl_c)
    points += 1 if data.first_degree_early_vascular_or_high_ldl else 0
    points += 2 if data.first_degree_xanthoma_or_child_high_ldl else 0
    points += 2 if data.personal_early_cad else 0
    points += 1 if data.personal_early_cerebral_or_pad else 0
    points += 6 if data.xanthoma else 0
    points += 4 if data.corneal_arcus_under_45 else 0
    points += 8 if data.functional_gene_mutation else 0

    if points > 8:
        classification = "Definite FH"
    elif points >= 6:
        classification = "Probable FH"
    elif points >= 3:
        classification = "Possible FH"
    else:
        classification = "Not meeting FH criteria"
    return FHScreeningResult(classification=classification, points=points)
