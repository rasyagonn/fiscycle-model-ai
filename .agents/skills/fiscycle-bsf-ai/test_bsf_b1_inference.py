"""Contract and artifact regression tests. Run after validation creates calibration."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from bsf_b1_inference import B1Predictor, FEATURES, predict_next_weight

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'hasil' / 'v2'
DETAIL = OUT / 'detail'
INTERNAL = OUT / 'internal'


class InferenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = B1Predictor(OUT.parent)
        cls.examples = json.loads((DETAIL / 'bsf_model_b1_replay_examples.json').read_text(encoding='utf-8'))

    def base(self):
        return dict(moisture_percent=55, elapsed_days=10, current_weight_mg=100,
                    previous_weight_mg=100, recent_growth_mg_per_day=0, forecast_horizon_days=1)

    def assert_rejected_without_estimator(self, payload, status=None):
        with patch.object(self.predictor.model, 'predict', side_effect=AssertionError('Estimator called for invalid input')) as mocked:
            result = self.predictor.predict(payload)
            mocked.assert_not_called()
        self.assertIsNone(result['predicted_next_weight_mg'])
        self.assertIsNone(result['uncertainty'])
        self.assertTrue(result['warnings'])
        self.assertNotEqual(result['input_domain_status'], 'IN_DOMAIN')
        if status:
            self.assertEqual(result['input_domain_status'], status)
        json.dumps(result, allow_nan=False)

    def test_missing_fields_and_unknown_fields(self):
        for key in FEATURES:
            payload = self.base()
            payload.pop(key)
            with self.subTest(key=key):
                self.assert_rejected_without_estimator(payload, 'INVALID_INPUT')
        self.assert_rejected_without_estimator({**self.base(), 'target_weight_mg': 120}, 'INVALID_INPUT')
        for payload in [None, [], 'invalid']:
            self.assert_rejected_without_estimator(payload, 'INVALID_INPUT')

    def test_non_finite_bool_and_non_numeric(self):
        for field in FEATURES:
            for value in [float('nan'), float('inf'), -float('inf'), True, None, '55', []]:
                with self.subTest(field=field, value=str(value)):
                    self.assert_rejected_without_estimator({**self.base(), field: value}, 'INVALID_INPUT')

    def test_treatment_and_range_bounds(self):
        for value in [44, 50, 85]:
            self.assert_rejected_without_estimator({**self.base(), 'moisture_percent': value}, 'OUT_OF_DOMAIN')
        for field in ['elapsed_days', 'forecast_horizon_days']:
            bounds = self.predictor.bounds[field]
            for value in [bounds['min'] - .01, bounds['max'] + .01]:
                self.assert_rejected_without_estimator({**self.base(), field: value}, 'OUT_OF_DOMAIN')
        for value in [1, 400]:
            self.assert_rejected_without_estimator({**self.base(), 'current_weight_mg': value, 'previous_weight_mg': value}, 'OUT_OF_DOMAIN')
        for current, previous, growth in [(200, 100, 200), (100, 200, -200)]:
            self.assert_rejected_without_estimator({**self.base(), 'current_weight_mg': current,
                'previous_weight_mg': previous, 'recent_growth_mg_per_day': growth}, 'OUT_OF_DOMAIN')

    def test_negative_and_inconsistent_history(self):
        for field in ['elapsed_days', 'forecast_horizon_days', 'current_weight_mg', 'previous_weight_mg']:
            self.assert_rejected_without_estimator({**self.base(), field: -1}, 'INVALID_INPUT')
        self.assert_rejected_without_estimator({**self.base(), 'forecast_horizon_days': 0}, 'INVALID_INPUT')
        for delta, rate in [(1, -1), (0, 1), (1, 0), (1, .01)]:
            self.assert_rejected_without_estimator({**self.base(), 'current_weight_mg': 100+delta,
                'recent_growth_mg_per_day': rate}, 'INVALID_INPUT')

    def test_supported_treatments_and_inclusive_bounds(self):
        for moisture in [45, 55, 65, 75]:
            self.assertEqual(self.predictor.predict({**self.base(), 'moisture_percent': moisture})['input_domain_status'], 'IN_DOMAIN')
        for field in ['elapsed_days', 'forecast_horizon_days']:
            for value in self.predictor.bounds[field].values():
                self.assertEqual(self.predictor.predict({**self.base(), field: value})['input_domain_status'], 'IN_DOMAIN')
        for value in self.predictor.bounds['current_weight_mg'].values():
            self.assertEqual(self.predictor.predict({**self.base(), 'current_weight_mg': value,
                'previous_weight_mg': value})['input_domain_status'], 'IN_DOMAIN')

    def test_replay_responses_and_json_serialization(self):
        for example in self.examples:
            payload = deepcopy(example['input'])
            output = predict_next_weight(payload, predictor=self.predictor)
            self.assertEqual(payload, example['input'])
            self.assertEqual(output['input_domain_status'], 'IN_DOMAIN')
            self.assertEqual(output['model_status'], 'RESEARCH_PROTOTYPE')
            self.assertEqual(output['validation_status'], 'NOT_FIELD_VALIDATED')
            self.assertAlmostEqual(output['predicted_next_weight_mg'], example['output']['predicted_next_weight_mg'])
            band = output['uncertainty']
            self.assertGreaterEqual(band['lower_mg'], 0)
            self.assertLessEqual(band['lower_mg'], output['predicted_next_weight_mg'])
            self.assertGreaterEqual(band['upper_mg'], output['predicted_next_weight_mg'])
            self.assertFalse(band['coverage_guaranteed'])
            json.dumps(output, allow_nan=False)
        self.assertFalse(self.examples[-1]['interval_contains_observation'])

    def test_all_holdout_predictions_match_saved_model(self):
        errors = pd.read_csv(DETAIL / 'bsf_model_b1_holdout_error_analysis.csv')
        for row in errors.to_dict('records'):
            output = self.predictor.predict({key: row[key] for key in FEATURES})
            self.assertEqual(output['input_domain_status'], row['input_domain_status'])
            if output['input_domain_status'] == 'IN_DOMAIN':
                self.assertAlmostEqual(output['predicted_next_weight_mg'], row['predicted_next_weight_mg'])

    def test_calibration_excludes_test_and_synthetic(self):
        oof = pd.read_csv(INTERNAL / 'bsf_model_b1_development_oof_residuals.csv')
        manifest = json.loads((INTERNAL / 'bsf_model_b1_oof_manifest.json').read_text(encoding='utf-8'))
        test_ids = set(self.predictor.metadata['excluded_final_test_replicates'])
        self.assertEqual(len(oof), 288)
        self.assertEqual(oof.replicate_id.nunique(), 16)
        self.assertFalse(set(oof.replicate_id) & test_ids)
        self.assertEqual(set(oof.data_provenance), {'PUBLIC_RESEARCH_DEVELOPMENT_OOF'})
        for fold in manifest['folds']:
            self.assertFalse(set(fold['train_replicates']) & set(fold['validation_replicates']))
            self.assertFalse((set(fold['train_replicates']) | set(fold['validation_replicates'])) & test_ids)
            actual = set(oof.loc[oof.fold == fold['fold'], 'replicate_id'])
            self.assertEqual(actual, set(fold['validation_replicates']))
        self.assertAlmostEqual(self.predictor.radius, np.quantile(oof.error_mg.abs(), .90, method='higher'))

    def test_stale_calibration_fails_before_model_load(self):
        with patch('bsf_b1_inference.file_hash', return_value='mismatched-hash'):
            with patch('bsf_b1_inference.joblib.load') as loader:
                with self.assertRaisesRegex(ValueError, 'Stale uncertainty calibration'):
                    B1Predictor(OUT.parent)
                loader.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
