import unittest
from pathlib import Path
from tracker.core import Task, schedule, cost_metrics, load_tasks

class SchedulingTests(unittest.TestCase):
    def test_parallel_paths_and_float(self):
        tasks = [Task('A','Start',2,[],100,80), Task('B','Long',4,['A'],200,220), Task('C','Short',1,['A'],100,100), Task('D','Finish',2,['B','C'],100,50)]
        result = schedule(tasks)
        self.assertEqual(result['D']['finish'], 8)
        self.assertEqual(result['C']['float'], 3)
        self.assertEqual([t.id for t in tasks if result[t.id]['float'] == 0], ['A','B','D'])

    def test_cycle_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            schedule([Task('A','A',1,['B'],1,1), Task('B','B',1,['A'],1,1)])

    def test_cost_metrics(self):
        self.assertEqual(cost_metrics(100, 80, 0.5), {'earned':50, 'variance':-30, 'forecast':160})
        self.assertIsNone(cost_metrics(100, 20, 0)['forecast'])


class SampleProjectTests(unittest.TestCase):
    def setUp(self):
        sample = Path(__file__).resolve().parents[1] / 'examples' / 'capital_project.csv'
        self.tasks = load_tasks(sample)

    def test_sample_dependency_timings_and_float(self):
        # B and C run in parallel after A; installation must wait for both.
        self.assertEqual(schedule(self.tasks), {
            'A': {'start': 0, 'finish': 5, 'latest_start': 0, 'float': 0},
            'B': {'start': 5, 'finish': 9, 'latest_start': 9, 'float': 4},
            'C': {'start': 5, 'finish': 13, 'latest_start': 5, 'float': 0},
            'D': {'start': 13, 'finish': 19, 'latest_start': 13, 'float': 0},
            'E': {'start': 19, 'finish': 22, 'latest_start': 19, 'float': 0},
        })

    def test_sample_earned_value_variance_and_forecast(self):
        # Expected values are calculated by hand from the committed CSV.
        expected = {
            'A': (12000, 1000, 11000),
            'B': (3000, 500, 4000 * 2500 / 3000),
            'C': (15000, -3000, 36000),
            'D': (0, 0, None),
            'E': (0, 0, None),
        }
        total_budget = total_actual = total_earned = total_variance = 0
        for task in self.tasks:
            with self.subTest(task=task.id):
                metrics = cost_metrics(task.budget, task.actual, task.progress)
                earned, variance, forecast = expected[task.id]
                self.assertEqual(metrics['earned'], earned)
                self.assertEqual(metrics['variance'], variance)
                if forecast is None:
                    self.assertIsNone(metrics['forecast'])
                else:
                    self.assertAlmostEqual(metrics['forecast'], forecast)
                total_budget += task.budget
                total_actual += task.actual
                total_earned += metrics['earned']
                total_variance += metrics['variance']

        self.assertEqual((total_budget, total_actual, total_earned, total_variance),
                         (74000, 31500, 30000, -1500))
        # Aggregate progress is weighted by budget, not averaged across tasks.
        total = cost_metrics(total_budget, total_actual, total_earned / total_budget)
        self.assertAlmostEqual(total['forecast'], 77700)
