import unittest
from unittest.mock import Mock, patch

from google.genai import types

from app.tools import riot_tool
from app.tools.riot_tool import RiotTools


class RiotTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {"RIOT_API_KEY": "test-secret"})
        self.env.start()
        riot_tool._blocked_until = 0
        self.tools = RiotTools()

    def tearDown(self):
        self.env.stop()
        riot_tool._blocked_until = 0

    @patch("app.tools.riot_tool.requests.get")
    def test_account_encoding_auth_and_cache(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"puuid": "p", "gameName": "A B", "tagLine": "EUW"}
        self.assertEqual(self.tools.riot_account("A B", "EUW")["puuid"], "p")
        self.tools.riot_account("A B", "EUW")
        get.assert_called_once()
        self.assertIn("A%20B/EUW", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["headers"], {"X-Riot-Token": "test-secret"})
        self.assertIn("error", self.tools.riot_account("a", "b", "evil.example"))

    @patch("app.tools.riot_tool.requests.get")
    def test_rate_limit_blocks_subsequent_calls(self, get):
        get.return_value = Mock(status_code=429, headers={"Retry-After": "60"})
        self.assertIn("60", self.tools.riot_account("a", "b")["error"])
        self.assertIn("rate limit", RiotTools().riot_account("c", "d")["error"])
        get.assert_called_once()

    def match(self, role="TOP", win=True, remake=False):
        return {"info": {"queueId": 420, "gameDuration": 1200, "gameVersion": "16.22.1",
                         "participants": [{"puuid": "p", "championName": "Garen", "teamPosition": role,
                                           "win": win, "kills": 4, "deaths": 0, "assists": 2,
                                           "totalMinionsKilled": 120, "neutralMinionsKilled": 20,
                                           "totalDamageDealtToChampions": 20000,
                                           "gameEndedInEarlySurrender": remake}]}}

    def test_statistics_separate_roles_and_exclude_remakes(self):
        self.tools._get = Mock(side_effect=[['a', 'b', 'c', 'd'], self.match(), self.match(win=False),
                                           self.match(role="JUNGLE"), self.match(remake=True)])
        result = self.tools.riot_analyze_champions("p")
        top = result["champions"][0]
        self.assertEqual(result["analyzed"], 3)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(top["games"], 2)
        self.assertEqual(top["win_rate"], 0.5)
        self.assertEqual(top["avg_cs_per_min"], 7)
        self.assertEqual(top["avg_damage_per_min"], 1000)
        self.assertEqual(top["patches"], ["16.22"])
        self.assertEqual(len(result["champions"]), 2)

    @patch("app.tools.riot_tool.requests.get")
    def test_partial_result_request_budget_and_validation(self, get):
        self.tools.remaining = 2
        # A list response followed by one match consumes the entire budget.
        responses = [Mock(status_code=200), Mock(status_code=200)]
        responses[0].json.return_value = ["a", "b"]
        responses[1].json.return_value = self.match()
        get.side_effect = responses
        result = self.tools.riot_analyze_champions("p")
        self.assertTrue(result["partial"])
        self.assertEqual(result["analyzed"], 1)
        self.assertEqual(result["next_start"], 1)
        self.assertEqual(get.call_count, 2)
        self.assertIn("error", self.tools.riot_match_history("p", count=101))
        self.assertIn("error", self.tools.riot_match_history("p", queue=450))

    def test_missing_key_and_gemini_schemas(self):
        self.tools.api_key = ""
        self.assertIn("RIOT_API_KEY", self.tools.riot_account("a", "b")["error"])
        for tool in (self.tools.riot_account, self.tools.riot_match_history, self.tools.riot_analyze_champions):
            declaration = types.FunctionDeclaration.from_callable(client=Mock(), callable=tool)
            self.assertEqual(declaration.name, tool.__name__)


if __name__ == "__main__":
    unittest.main()
