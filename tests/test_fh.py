import unittest

from statin_nhi.fh import FHScreeningData, evaluate_fh_screening


class FHScreeningTests(unittest.TestCase):
    def test_ldl_score_boundaries_and_classifications(self) -> None:
        cases = [
            (154, 0, "Not meeting FH criteria"),
            (155, 1, "Not meeting FH criteria"),
            (190, 3, "Possible FH"),
            (250, 5, "Possible FH"),
            (330, 8, "Probable FH"),
        ]
        for ldl_c, expected_points, expected_classification in cases:
            with self.subTest(ldl_c=ldl_c):
                result = evaluate_fh_screening(FHScreeningData(), ldl_c)
                self.assertEqual(result.points, expected_points)
                self.assertEqual(result.classification, expected_classification)

    def test_manual_evidence_is_added_to_automatic_ldl_score(self) -> None:
        result = evaluate_fh_screening(FHScreeningData(xanthoma=True), 190)
        self.assertEqual(result.popup_text, "Definite FH (9 points)")
        self.assertEqual(result.output_text, "TW FH dx criteria: Definite FH (9 points)")

    def test_probable_and_possible_boundaries(self) -> None:
        probable = evaluate_fh_screening(FHScreeningData(first_degree_xanthoma_or_child_high_ldl=True), 250)
        possible = evaluate_fh_screening(FHScreeningData(first_degree_early_vascular_or_high_ldl=True), 190)
        self.assertEqual(probable.popup_text, "Probable FH (7 points)")
        self.assertEqual(possible.popup_text, "Possible FH (4 points)")


if __name__ == "__main__":
    unittest.main()
