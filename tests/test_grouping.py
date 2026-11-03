import unittest
from unittest.mock import patch

from grouping import best, group_case, load_rules, matched_operation_count


DATA = load_rules()


def group(diagnoses, operations=None, **extra):
    return group_case(DATA, {"diagnoses": diagnoses, "operations": operations or [], **extra})


class GroupingTests(unittest.TestCase):
    def test_rule_count(self):
        sections = ("xq", "bx", "fz_burn", "fz_tumor", "fz_tb", "jc")
        self.assertEqual(sum(len(DATA["sheets"][key]["rows"]) for key in sections), 5125)

    def test_j18_paths(self):
        self.assertEqual(group(["J18.900"])["hit"]["key"], "JC-3414")
        self.assertEqual(group(["J18.900"], ["33.2402"])["hit"]["key"], "BX-774")
        conservative = group(["J18.900"], ["17.91350"])
        self.assertEqual(conservative["hit"]["key"], "JC-3414")
        self.assertIn("不保证最终命中基础规则", conservative["trace"][1]["detail"])
        self.assertEqual(group(["J18.900"], ["17.91350", "96.7201"])["hit"]["key"], "XQ-14")
        self.assertEqual(group(["J18.900"], ["96.7101"])["hit"]["key"], "JC-3413")

    def test_exact_diagnosis_exclusion(self):
        self.assertEqual(group(["J18.800"])["status"], "excluded")
        self.assertEqual(group(["J18.801"])["hit"]["key"], "JC-3414")

    def test_xq_related_operations(self):
        self.assertEqual(group(["J18.900"], ["96.7201"])["hit"]["key"], "XQ-14")
        self.assertEqual(group(["J18.900"], ["96.7201", "39.9500x007"])["hit"]["key"], "XQ-13")

    def test_tumor_auxiliary(self):
        self.assertEqual(group(["Z51.101", "C34.901"], ["99.2503"])["hit"]["key"], "FZ-1770")
        combined = group(["Z51.101", "C34.901"], ["99.2503", "99.2800x005"])
        self.assertEqual(combined["hit"]["key"], "FZ-1771")
        self.assertEqual(combined["hit"]["conditionCount"], 4)
        self.assertEqual(combined["hit"]["score"], 121)
        self.assertEqual((combined["alternatives"][0]["key"], combined["alternatives"][0]["conditionCount"]),
                         ("FZ-1770", 3))
        self.assertEqual(combined["alternatives"][0]["score"], 111)
        self.assertNotEqual((group(["Z51.101", "C34.901"], ["99.2800x005", "99.2503"])["hit"] or {}).get("key"), "FZ-1771")
        self.assertNotEqual((group(["Z51.101"], ["99.2503"])["hit"] or {}).get("key"), "FZ-1770")

    def test_newborn(self):
        self.assertEqual(group(["P07.000"], ageDays=10, birthWeight=900)["hit"]["key"], "XQ-16")
        self.assertNotEqual((group(["P07.000"], ageDays=29, birthWeight=900)["hit"] or {}).get("key"), "XQ-16")

    def test_burn_and_tb(self):
        self.assertEqual(group(["T20.200", "T31.000"])["hit"]["key"], "FZ-1745")
        self.assertEqual(group(["A15.000x010"], ["31.9400"])["hit"]["key"], "FZ-1812")

    def test_forbidden_main_operation(self):
        result = group(["J18.900"], ["00.3101"])
        self.assertEqual(result["status"], "invalid_operation")
        self.assertIn("不可作为主要手术操作", result["message"])

    def test_grassroots(self):
        self.assertEqual([x["number"] for x in group(["J18.900"])["grassroots"]], ["38"])
        self.assertEqual([x["number"] for x in group(["J18.900"], ["17.91350"])["grassroots"]], ["38"])
        self.assertEqual(group(["J18.900"], ["33.2402"])["grassroots"], [])
        self.assertEqual(group(["J18.900"], ["17.91350", "96.7201"])["grassroots"], [])

    def test_diagnosis_exclusion_precedes_operation(self):
        result = group(["J18.800"], ["17.91350"])
        self.assertEqual(result["status"], "excluded")
        self.assertEqual(len(result["trace"]), 1)

    def test_conditional_operation(self):
        self.assertEqual(group(["J18.900"], ["44.1300x001"])["status"], "invalid_operation")
        allowed = group(["K29.700"], ["44.1300x001"])
        self.assertEqual(allowed["hit"]["key"], "BX-903")
        self.assertIn("满足例外范围", allowed["trace"][1]["detail"])

    def test_candidate_condition_priority_and_matched_alternative(self):
        self.assertEqual(matched_operation_count("A+B|A", ["A"]), 1)
        self.assertEqual(matched_operation_count("A+B|A", ["A", "B"]), 2)
        candidates = [
            {"number": "1", "score": 200, "conditionCount": 2},
            {"number": "2", "score": 100, "conditionCount": 3},
        ]
        self.assertIs(best(candidates), candidates[1])
        candidates[0]["conditionCount"] = 3
        self.assertIs(best(candidates), candidates[0])
        candidates[0]["score"] = 100
        self.assertIs(best(candidates), candidates[0])

    def test_all_other_candidates_remain_alternatives(self):
        candidates = [{"key": f"XQ-{number}", "number": str(number), "section": "xq",
                       "row": number + 3, "conditionCount": number, "score": 100}
                      for number in range(1, 9)]
        with patch("grouping.xq_candidates", return_value=candidates):
            result = group(["J18.900"])
        self.assertEqual(result["hit"]["key"], "XQ-8")
        self.assertEqual([hit["key"] for hit in result["alternatives"]],
                         [f"XQ-{number}" for number in range(7, 0, -1)])


if __name__ == "__main__":
    unittest.main()
