import unittest

from drg_grouping import DATA, EXCL, Parser, group_case, search_catalog


def grouped(diagnoses, operations=(), *, sex="男", age=30, age_days=None, weight=None):
    return group_case({
        "diagnoses": diagnoses, "operations": list(operations), "sex": sex,
        "age": age, "ageDays": age_days, "admissionWeight": weight,
        "lengthOfStay": 15,
    })


class DrgGroupingTests(unittest.TestCase):
    def test_six_live_comparisons(self):
        cases = [
            (["J18.000"], [], "ES45", "0.3954", "3854.10"),
            (["J18.000", "N39.000"], [], "ES43", "0.6181", "6024.52"),
            (["J18.000", "N17.900"], [], "ES41", "0.9769", "9521.40"),
            (["J18.000", "N39.000", "N17.900"], [], "ES41", "0.9769", "9521.40"),
            (["J18.000"], ["96.7201", "33.2400x001"], "AH39", "7.0137", "68357.89"),
            (["J18.000"], ["33.2400x001", "96.7201"], "EK35", "0.9525", "9283.72"),
        ]
        for diagnoses, operations, code, weight, fee in cases:
            with self.subTest(code=code, diagnoses=diagnoses, operations=operations):
                result = grouped(diagnoses, operations)
                self.assertEqual((result["hit"]["code"], result["hit"]["weight"],
                                  result["hit"]["fee"]), (code, weight, fee))

    def test_gender_age_and_newborn_boundaries(self):
        self.assertEqual(grouped(["C49.503"], sex="男")["hit"]["code"], "MR15")
        self.assertEqual(grouped(["C49.503"], sex="女")["hit"]["code"], "NR15")
        self.assertEqual(grouped(["A37.900"], age=6)["hit"]["code"], "EX2D")
        self.assertEqual(grouped(["A37.900"], age=7)["hit"]["code"], "EX29")
        for weight, expected in [(999, "PS19"), (1000, "PS29"), (2499, "PS45"), (2500, "PS55")]:
            with self.subTest(weight=weight):
                self.assertEqual(grouped(["P07.300x001"], age=0, age_days=7,
                                         weight=weight)["hit"]["code"], expected)

    def test_cc_exclusion_and_invalid_weight(self):
        primary = next(code for code in EXCL["EX_45"] if code != "I50.900X001")
        evaluator = Parser([], {"ZYZD": primary})
        self.assertIsNone(evaluator.ccLevel("I50.900X001"))
        with self.assertRaisesRegex(ValueError, "入院体重只能填写"):
            grouped(["P07.300x001"], age=0, age_days=7, weight="999g")

    def test_reference_and_code_dictionary(self):
        self.assertEqual(len(DATA["reference"]), 825)
        self.assertIsNone(DATA["reference"]["AA19"]["fee"])
        no_reference = grouped(["J18.000"], ["33.6x00"])["hit"]
        self.assertEqual(no_reference["code"], "AA19")
        self.assertIsNone(no_reference["weight"])
        self.assertIsNone(no_reference["fee"])
        self.assertEqual(search_catalog("dx", "J18.000")[0]["name"], "支气管肺炎")
        self.assertEqual(search_catalog("op", "96.7201")[0]["code"], "96.7201")


if __name__ == "__main__":
    unittest.main()
