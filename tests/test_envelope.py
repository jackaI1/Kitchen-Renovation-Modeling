import unittest
from renovation.envelope import Layer, analyze, saturation_pressure

class EnvelopeTests(unittest.TestCase):
    def test_temperature_and_vapour_profile(self):
        layers = [Layer('inside', 0.1, 0.1, 100, ('air', 'vapour')), Layer('outside', 0.1, 0.1, 100, ('water', 'thermal'))]
        r = analyze(layers, 20, -10, 0.5, 0.8)
        self.assertAlmostEqual(r['rsi'], 2)
        self.assertAlmostEqual(r['interfaces'][0]['temperature_c'], 5)
        expected = (0.5 * saturation_pressure(20) + 0.8 * saturation_pressure(-10)) / 2
        self.assertAlmostEqual(r['interfaces'][0]['vapour_pressure_pa'], expected)
        self.assertEqual(r['missing_controls'], [])

    def test_missing_and_wrong_side_control(self):
        r = analyze([Layer('insulation', 0.1, 0.04, 100, ('thermal',)), Layer('film', 0.001, 0.2, 5, ('vapour',))], 20, -10, .5, .8)
        self.assertEqual(r['missing_controls'], ['air', 'water'])
        self.assertTrue(r['warnings'])

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            analyze([Layer('bad', 0, 1, 1)], 20, -10, .5, .8)
        with self.assertRaises(ValueError):
            analyze([Layer('ok', 1, 1, 1)], 20, -10, 1.1, .8)
