import json
from pathlib import Path
import unittest

from statin_nhi.models import PatientData
from statin_nhi.parser import parse_note
from statin_nhi.rules import evaluate_new_eligibility
from statin_nhi.ui import App


CASE_FILE = Path(__file__).with_name("clinical_cases.json")


class ClinicalCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))

    def test_clinical_cases(self) -> None:
        patient_fields = set(PatientData.__dataclass_fields__)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                note = case.get("note", "")
                parsed = parse_note(note) if note else None
                for field_name, expected_value in case.get("expected_extracted", {}).items():
                    self.assertEqual(parsed.extracted_fields.get(field_name), expected_value)
                for field_name in case.get("expected_absent_extracted", []):
                    self.assertNotIn(field_name, parsed.extracted_fields)

                patient_kwargs = case["patient"]
                self.assertTrue(set(patient_kwargs).issubset(patient_fields), "案例使用不存在的 PatientData 欄位")
                patient = PatientData(**patient_kwargs)
                outcome = evaluate_new_eligibility(patient)
                expected = case["expected"]
                self.assertEqual(outcome.risk_category, expected["risk_category"])
                for condition in expected.get("matched_contains", []):
                    self.assertIn(condition, outcome.matched_conditions)

                output = "\n".join(App._format_eligibility_output(None, patient, outcome))
                for text in expected.get("output_contains", []):
                    self.assertIn(text, output)
                for text in expected.get("output_absent", []):
                    self.assertNotIn(text, output)


if __name__ == "__main__":
    unittest.main()
