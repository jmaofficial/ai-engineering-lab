import json
import tempfile
import unittest
import os
from unittest.mock import Mock

from google.genai import types
from app.tools.analysis_tool import AnalysisTools
from app.tools.riot_tool import RiotError


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.riot = Mock(max_matches=20, remaining=30)
        self.tools = AnalysisTools(self.riot, self.temp.name)
        self.match = {'metadata': {'matchId': 'EUW1_1'}, 'info': {'queueId': 420,
            'gameDuration': 1200, 'gameVersion': '16.22.1', 'participants': [
                {'puuid': 'p', 'championName': 'Orianna', 'teamPosition': 'MIDDLE',
                 'win': True, 'kills': 4, 'teamId': 100}]}}

    def tearDown(self):
        self.temp.cleanup()

    def test_persistence_dedup_and_exhaustion(self):
        self.riot._get.side_effect = [['EUW1_1'], self.match, ['EUW1_1'], []]
        first = self.tools.collect_match_dataset('p')
        second = AnalysisTools(self.riot, self.temp.name).collect_match_dataset('p')
        self.assertEqual(first['stored_matches'], 1)
        self.assertEqual(second['added'], 0)
        self.assertFalse(second['history_exhausted'])
        self.assertTrue(self.tools.collect_match_dataset('p', start=1)['history_exhausted'])
        profile = self.tools.inspect_match_dataset(first['dataset_id'])
        self.assertEqual(profile['next_start'], 1)
        self.assertTrue(profile['history_exhausted'])
        self.assertEqual(profile['roles'], {'MIDDLE': 1})
        self.assertEqual(profile['remake_flags'], {'UNKNOWN': 1})

    def test_partial_cursor(self):
        self.riot._get.side_effect = [['EUW1_1', 'EUW1_2'], self.match, RiotError('rate limited')]
        result = self.tools.collect_match_dataset('p', start=5)
        self.assertEqual(result['next_start'], 6)
        self.assertEqual(result['stored_matches'], 1)
        self.assertEqual(result['error'], 'rate limited')
        self.assertEqual(self.tools.inspect_match_dataset(result['dataset_id'])['next_start'], 0)

    def test_schema_and_invalid_dataset(self):
        for method in (self.tools.collect_match_dataset, self.tools.collect_more_matches,
                       self.tools.inspect_match_dataset, self.tools.analyze_match_dataset):
            schema = types.FunctionDeclaration.from_callable(client=Mock(), callable=method)
            self.assertEqual(schema.name, method.__name__)
        self.assertIn('error', self.tools.analyze_match_dataset('../secret', 'print(1)', 'test'))
        self.assertIn('error', self.tools.analyze_match_dataset('a' * 24, 'print(1)', 'test'))

    def test_continuation_uses_saved_account_and_cursor(self):
        self.riot._get.side_effect = [['EUW1_1'], self.match, []]
        first = self.tools.collect_match_dataset('p', count=1)
        continued = self.tools.collect_more_matches(first['dataset_id'], count=1)
        self.assertTrue(continued['history_exhausted'])
        self.assertEqual(self.riot._get.call_args.args[2]['start'], 1)
        self.assertIn('/p/ids', self.riot._get.call_args.args[1])

    def test_http_failure_is_never_history_exhaustion(self):
        self.riot._get.side_effect = RiotError('HTTP 400')
        result = self.tools.collect_match_dataset('p')
        self.assertFalse(result['history_exhausted'])
        self.assertEqual(result['collection_status'], 'blocked')

    @unittest.skipUnless(os.getenv('RUN_CONTAINER_TESTS') == '1', 'Set RUN_CONTAINER_TESTS=1 to test Docker execution')
    def test_container_profiles_track_actual_filters_and_code_repair(self):
        remake = json.loads(json.dumps(self.match))
        remake['metadata']['matchId'] = 'EUW1_2'
        remake['info']['participants'][0]['gameEndedInEarlySurrender'] = True
        self.match['info']['participants'][0]['gameEndedInEarlySurrender'] = False
        self.riot._get.side_effect = [['EUW1_1', 'EUW1_2'], self.match, remake]
        dataset_id = self.tools.collect_match_dataset('p')['dataset_id']
        failed = self.tools.analyze_match_dataset(dataset_id, "print(df['not_a_column'])", 'Check recovery from a missing column')
        self.assertFalse(failed['success'])
        result = self.tools.analyze_match_dataset(dataset_id,
            "df_mid = df[(df.teamPosition == 'MIDDLE') & (df.gameEndedInEarlySurrender == False)].copy()\nprint(proportion_ci(5,10))",
            'Exclude flagged remakes and calculate a Wilson interval')
        self.assertTrue(result['success'], result)
        self.assertEqual(result['input_profile']['rows'], 2)
        self.assertEqual(result['frame_profiles']['df_mid']['rows'], 1)
        self.assertEqual(result['input_profile']['gameEndedInEarlySurrender'], {'False': 1, 'True': 1})
        self.assertNotIn('__ANALYSIS_METADATA__', result['output'])


if __name__ == '__main__':
    unittest.main()
