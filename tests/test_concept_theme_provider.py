import unittest

from trade_signal_tool.providers.concept_theme_provider import ConceptThemeProvider


class FakeFrame:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        self.assert_orient = orient
        return self.records


class ConceptThemeAkshare:
    def __init__(self):
        self.concept_symbols = []

    def stock_board_concept_name_em(self):
        return FakeFrame(
            [
                {"板块名称": "机器人", "涨跌幅": 3.8},
                {"板块名称": "人工智能", "涨跌幅": 5.2},
                {"板块名称": "低空经济", "涨跌幅": 1.4},
            ]
        )

    def stock_board_concept_cons_em(self, symbol):
        self.concept_symbols.append(symbol)
        records = {
            "人工智能": [
                {"代码": "300001", "名称": "示例科技"},
                {"代码": "000001", "名称": "平安银行"},
            ],
            "机器人": [
                {"代码": "300001", "名称": "示例科技"},
                {"代码": "300002", "名称": "好日线"},
            ],
            "低空经济": [
                {"代码": "300003", "名称": "低空样本"},
            ],
        }
        return FakeFrame(records[symbol])


class FailingConstituentAkshare(ConceptThemeAkshare):
    def stock_board_concept_cons_em(self, symbol):
        if symbol == "人工智能":
            raise RuntimeError("constituents disconnected")
        return super().stock_board_concept_cons_em(symbol)


class ConceptThemeProviderTest(unittest.TestCase):
    def test_assigns_strongest_concept_when_stock_belongs_to_multiple_hot_concepts(self):
        ak = ConceptThemeAkshare()
        provider = ConceptThemeProvider(ak, hot_concept_limit=2)

        assignments = provider.assignments_for_codes(["300001", "000001", "300002"])

        self.assertEqual(assignments["300001"].theme, "人工智能")
        self.assertEqual(assignments["300001"].theme_rank, 1)
        self.assertEqual(assignments["000001"].theme, "人工智能")
        self.assertEqual(assignments["000001"].theme_rank, 1)
        self.assertEqual(assignments["300002"].theme, "机器人")
        self.assertEqual(assignments["300002"].theme_rank, 2)
        self.assertEqual(ak.concept_symbols, ["人工智能", "机器人"])

    def test_skips_failed_constituent_request_and_keeps_next_hot_concept(self):
        provider = ConceptThemeProvider(FailingConstituentAkshare(), hot_concept_limit=2)

        assignments = provider.assignments_for_codes(["300001", "300002"])

        self.assertEqual(assignments["300001"].theme, "机器人")
        self.assertEqual(assignments["300001"].theme_rank, 2)
        self.assertEqual(assignments["300002"].theme, "机器人")
        self.assertEqual(assignments["300002"].theme_rank, 2)


if __name__ == "__main__":
    unittest.main()
