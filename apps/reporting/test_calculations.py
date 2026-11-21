import unittest
from decimal import Decimal as D
from apps.reporting.calculations import Evidence, skill_summary, skill_trend, rank_results


def e(attempt, points, maximum='10', topic='grammar', skill='WRITING', difficulty='FOUNDATION'):
    return Evidence(attempt, skill, D(points), D(maximum), difficulty, frozenset([topic]))


class CalculationsTests(unittest.TestCase):
    def test_weighted_score_and_sample(self):
        r = skill_summary([e('a','2','4'),e('b','3','6')], 'WRITING')
        self.assertEqual(r['percent'], D('50.00'))
        self.assertEqual(r['label'], 'REINFORCING')
        self.assertIsNone(skill_summary([e('a','2','4')], 'WRITING')['label'])
        self.assertIsNone(skill_summary([], 'READING')['percent'])

    def test_trend_matched_topics(self):
        old = [e('a','9'),e('b','9')]
        now = [e('c','6'),e('d','6')]
        self.assertEqual(skill_trend(now, old, 'WRITING')['trend'], 'DOWN')
        self.assertIsNone(skill_trend([e('c','6',topic='other'),e('d','6',topic='other')], old, 'WRITING')['trend'])

    def test_competition_ranking_and_incomplete(self):
        scores = {'a':[(9,10)], 'b':[(8,10)], 'c':[(8,10)], 'd':[(7,10)], 'e':[None]}
        result = rank_results(scores,1)
        self.assertEqual([result[x]['rank'] for x in 'abcd'], [1,2,2,4])
        self.assertEqual(result['e']['status'],'INCOMPLETE')
        self.assertEqual(rank_results({'x':[(8,10),(60,100)]},2)['x']['score'],D('70.00'))

    def test_invalid_values(self):
        with self.assertRaises(ValueError): rank_results({'a':[(11,10)]},1)
        with self.assertRaises(ValueError): rank_results({'a':[]},1)

if __name__ == '__main__': unittest.main()
