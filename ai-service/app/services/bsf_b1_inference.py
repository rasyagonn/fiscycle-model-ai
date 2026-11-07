"""Reusable, offline B1 inference. Load only trusted local joblib artifacts."""
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
import hashlib
import json
import math

import joblib
import numpy as np
import pandas as pd
import sklearn

FEATURES = (
    'moisture_percent', 'elapsed_days', 'current_weight_mg',
    'previous_weight_mg', 'recent_growth_mg_per_day', 'forecast_horizon_days',
)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class B1Predictor:
    """Load once per process, then call predict with the six input fields."""

    def __init__(self, artifact_dir=None):
        module_dir = Path(__file__).resolve().parent
        if artifact_dir:
            folder = Path(artifact_dir)
        elif (module_dir / 'bsf_model_b1_estimator.joblib').is_file():
            # Portable four-file bundle: inference and artifacts are colocated.
            folder = module_dir
        else:
            # Development workspace layout.
            folder = module_dir / 'hasil'
        model_path = folder / 'bsf_model_b1_estimator.joblib'
        metadata_path = folder / 'bsf_model_b1_model_metadata.json'
        self.metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        calibration_candidates = [
            folder / 'bsf_model_b1_uncertainty.json',
            folder / 'v2' / 'internal' / 'bsf_model_b1_uncertainty.json',
        ]
        calibration_path = next((path for path in calibration_candidates if path.is_file()), None)
        if calibration_path is None:
            raise FileNotFoundError('Compatible B1 uncertainty artifact not found.')
        self.calibration = json.loads(calibration_path.read_text(encoding='utf-8'))
        if list(FEATURES) != self.metadata['features']:
            raise ValueError('Artifact feature schema mismatch.')
        for key, path in [('model_sha256', model_path), ('metadata_sha256', metadata_path)]:
            if self.calibration[key] != file_hash(path):
                raise ValueError('Stale uncertainty calibration: ' + key)
        if self.calibration['scikit_learn_version'] != sklearn.__version__:
            raise ValueError('Use the scikit-learn version recorded in uncertainty metadata.')
        self.bounds = self.metadata['feature_bounds_from_development_data']
        self.moistures = self.metadata['supported_moisture_treatments_percent']
        self.radius = float(self.calibration['absolute_error_radius_mg'])
        if not math.isfinite(self.radius) or self.radius < 0:
            raise ValueError('Invalid uncertainty artifact.')
        self.model = joblib.load(model_path)

    def predict(self, inputs):
        """Return JSON-safe output; malformed/OOD inputs never reach the estimator."""
        result = {
            'predicted_next_weight_mg': None,
            'input_domain_status': 'INVALID_INPUT',
            'warnings': [],
            'uncertainty': None,
            'model_status': 'RESEARCH_PROTOTYPE',
            'validation_status': 'NOT_FIELD_VALIDATED',
            'model_method': self.metadata['method'],
            'training_source': self.metadata['training_source'],
            'contract_version': '1.0',
        }
        messages = result['warnings']
        if not isinstance(inputs, Mapping):
            messages.append('EXPECTED_OBJECT: supply the six numeric input fields.')
            return result
        missing = sorted(set(FEATURES) - inputs.keys())
        extra = sorted(str(key) for key in inputs.keys() - set(FEATURES))
        if missing:
            messages.append('MISSING_FIELDS: ' + ', '.join(missing))
        if extra:
            messages.append('UNKNOWN_FIELDS: ' + ', '.join(extra))
        for key in FEATURES:
            if key in inputs:
                value = inputs[key]
                if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
                    messages.append('INVALID_NUMBER: ' + key)
                elif not math.isfinite(float(value)):
                    messages.append('NON_FINITE_NUMBER: ' + key)
        if messages:
            return result
        values = {key: float(inputs[key]) for key in FEATURES}
        for key in ['elapsed_days', 'current_weight_mg', 'previous_weight_mg']:
            if values[key] < 0:
                messages.append('NEGATIVE_VALUE: ' + key)
        if values['forecast_horizon_days'] <= 0:
            messages.append('NON_POSITIVE_HORIZON')
        change = values['current_weight_mg'] - values['previous_weight_mg']
        growth = values['recent_growth_mg_per_day']
        if (change == 0) != (growth == 0) or change * growth < 0:
            messages.append('INCONSISTENT_HISTORY: weight change and recent growth must agree.')
        elif growth != 0 and change / growth > values['elapsed_days'] + 1e-9:
            messages.append('INCONSISTENT_HISTORY: implied previous observation precedes elapsed day zero.')
        if messages:
            return result
        if values['moisture_percent'] not in self.moistures:
            messages.append('UNSUPPORTED_MOISTURE: supported treatments are 45, 55, 65, 75 percent.')
        for key, bounds in self.bounds.items():
            # Tiny tolerance handles floating point round trips only; never clip inputs.
            value = values[key]
            if value < bounds['min'] - 1e-9 or value > bounds['max'] + 1e-9:
                messages.append(f"OUT_OF_RANGE: {key} must be in [{bounds['min']}, {bounds['max']}].")
        if messages:
            result['input_domain_status'] = 'OUT_OF_DOMAIN'
            return result
        prediction = float(self.model.predict(pd.DataFrame([values], columns=FEATURES))[0])
        if not math.isfinite(prediction):
            result['input_domain_status'] = 'MODEL_ERROR'
            messages.append('NON_FINITE_MODEL_OUTPUT')
            return result
        prediction = max(0.0, prediction)
        result['predicted_next_weight_mg'] = prediction
        result['input_domain_status'] = 'IN_DOMAIN'
        result['uncertainty'] = {
            'method': 'development_group_oof_absolute_residual_quantile',
            'lower_mg': max(0.0, prediction - self.radius),
            'upper_mg': prediction + self.radius,
            'absolute_error_radius_mg': self.radius,
            'residual_quantile': self.calibration['residual_quantile'],
            'calibration_rows': self.calibration['n_residuals'],
            'calibration_replicates': len(self.calibration['replicate_ids']),
            'coverage_guaranteed': False,
        }
        messages.extend([
            'EMPIRICAL_BAND_ONLY: correlated residuals and reused model-selection folds; no individual confidence guarantee.',
            'DOMAIN_CHECK_LIMITED: marginal numeric bounds do not validate substrate, site, or joint input combinations.',
            'CALLER_VERIFY: weights in mg/individual; growth from actual ordered history; horizon known at prediction time.',
        ])
        if growth < 0:
            messages.append('RECENT_WEIGHT_DECREASE: retained observation; review measurement context.')
        return result


def predict_next_weight(inputs, *, predictor=None):
    """Convenience function; pass a preloaded B1Predictor for repeated requests."""
    return (predictor or B1Predictor()).predict(inputs)
