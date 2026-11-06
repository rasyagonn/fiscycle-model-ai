"""Reproduce B1 validation from saved artifacts; four fold fits only on cache miss."""
from pathlib import Path
import hashlib
import json

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone

from bsf_b1_inference import B1Predictor, FEATURES, file_hash

PHASES = ['early_<=6d', 'middle_6-13d', 'late_>13d']


def phase(values):
    return pd.cut(values, [-np.inf, 6, 13, np.inf], labels=PHASES).astype(str)


def records(frame):
    return json.loads(frame.to_json(orient='records', double_precision=12))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def md_table(frame):
    return '| ' + ' | '.join(frame.columns) + ' |\n' + '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |\n' + '\n'.join(
        '| ' + ' | '.join(f'{x:.3f}' if isinstance(x, float) else str(x) for x in row) + ' |'
        for row in frame.itertuples(index=False, name=None))


def make_pairs(raw):
    df = raw.sort_values(['replicate_id', 'elapsed_days']).copy()
    assert not df.duplicated(['replicate_id', 'elapsed_days']).any()
    g = df.groupby('replicate_id')
    df['previous_weight_mg'] = g['larval_wet_weight_mg'].shift(1)
    df['previous_elapsed_days'] = g['elapsed_days'].shift(1)
    df['target_weight_mg'] = g['larval_wet_weight_mg'].shift(-1)
    df['target_elapsed_days'] = g['elapsed_days'].shift(-1)
    df['current_weight_mg'] = df['larval_wet_weight_mg']
    df['history_interval_days'] = df['elapsed_days'] - df['previous_elapsed_days']
    df['recent_growth_mg_per_day'] = (df['current_weight_mg'] - df['previous_weight_mg']) / df['history_interval_days']
    df['forecast_horizon_days'] = df['target_elapsed_days'] - df['elapsed_days']
    transitions = df.dropna(subset=['target_weight_mg']).copy()
    transitions['change_mg'] = transitions['target_weight_mg'] - transitions['current_weight_mg']
    transitions['decrease'] = transitions['change_mg'] < 0
    transitions['phase_at_t'] = phase(transitions['elapsed_days'])
    transitions['phase_at_target'] = phase(transitions['target_elapsed_days'])
    transitions['target_elapsed_day_bin'] = np.floor(transitions['target_elapsed_days']).astype(int)
    pairs = transitions.dropna(subset=['previous_weight_mg']).copy()
    assert len(transitions) == 380 and len(pairs) == 360
    return transitions, pairs


def decrease_table(frame, keys):
    rows = []
    keys = [keys] if isinstance(keys, str) else keys
    for labels, group in frame.groupby(keys, observed=True):
        labels = labels if isinstance(labels, tuple) else (labels,)
        drops = group.loc[group.decrease, 'change_mg']
        rows.append({**dict(zip(keys, labels)), 'transitions': len(group),
                     'decreases': int(group.decrease.sum()), 'decrease_rate_pct': float(100 * group.decrease.mean()),
                     'mean_drop_mg': float(-drops.mean()) if len(drops) else 0.0,
                     'largest_drop_mg': float(-drops.min()) if len(drops) else 0.0})
    return pd.DataFrame(rows)


def error_stats(group):
    e = group.error_mg
    a = e.abs()
    return {'n': len(group), 'mae_mg': float(a.mean()), 'rmse_mg': float(np.sqrt((e**2).mean())),
            'bias_mg': float(e.mean()), 'median_abs_error_mg': float(a.median()),
            'p90_abs_error_mg': float(a.quantile(.9)), 'max_abs_error_mg': float(a.max()),
            'overprediction_count': int((e > 0).sum()),
            'interval_coverage_pct': float(100 * group.covered.mean()) if 'covered' in group else None}


def error_table(frame, keys):
    keys = [keys] if isinstance(keys, str) else keys
    rows = []
    for labels, group in frame.groupby(keys, observed=True):
        labels = labels if isinstance(labels, tuple) else (labels,)
        rows.append({**dict(zip(keys, labels)), **error_stats(group)})
    return pd.DataFrame(rows)


def run_validation(root=None):
    root = Path(root) if root else Path(__file__).resolve().parent
    artifact_root = root / 'hasil'
    out = artifact_root / 'v2'
    detail = out / 'detail'
    internal = out / 'internal'
    for folder in [out, detail, internal]:
        folder.mkdir(parents=True, exist_ok=True)
    raw_path = root / 'data' / 'Fiscycle_BSF_SubstrateMoisture_LongForm_400rows.csv'
    workbook = root / 'data' / 'Impact of substrate moisture content on BSF larvae Data.xlsx'
    model_path = artifact_root / 'bsf_model_b1_estimator.joblib'
    meta_path = artifact_root / 'bsf_model_b1_model_metadata.json'
    protected = [raw_path, workbook, model_path, meta_path]
    before = {p.name: file_hash(p) for p in protected}
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    original = json.loads((artifact_root / 'bsf_model_b1_evaluation_summary.json').read_text(encoding='utf-8'))
    assert file_hash(raw_path) == original['source']['derived_csv_sha256']
    assert file_hash(workbook) == original['source']['workbook_sha256']
    model = joblib.load(model_path)
    transitions, pairs = make_pairs(pd.read_csv(raw_path))
    dev = pairs[pairs.replicate_id.isin(meta['development_replicates'])].copy()
    test = pairs[pairs.replicate_id.isin(meta['excluded_final_test_replicates'])].copy()
    assert len(dev) == 288 and len(test) == 72 and set(dev.replicate_id).isdisjoint(test.replicate_id)
    drops = transitions[transitions.decrease].copy()
    assert len(drops) == 114
    audit_columns = ['replicate_id', 'moisture_percent', 'measurement_index_1based', 'elapsed_days',
                     'target_elapsed_days', 'current_weight_mg', 'target_weight_mg', 'change_mg',
                     'decrease', 'phase_at_t', 'phase_at_target', 'target_elapsed_day_bin']
    transitions[audit_columns].to_csv(detail / 'bsf_model_b1_all_transitions.csv', index=False)
    drops[audit_columns].to_csv(detail / 'bsf_model_b1_weight_decreases.csv', index=False)
    decrease_tables = {name: decrease_table(transitions, key) for name, key in {
        'moisture': 'moisture_percent', 'phase': 'phase_at_target', 'day': 'target_elapsed_day_bin',
        'replicate': 'replicate_id', 'moisture_phase': ['moisture_percent', 'phase_at_target'],
    }.items()}
    for name, table in decrease_tables.items():
        table.to_csv(detail / f'bsf_model_b1_decreases_by_{name}.csv', index=False)

    # Fixed selected estimator settings. No search, no final-model fit, no test residual calibration.
    cache_path = internal / 'bsf_model_b1_development_oof_residuals.csv'
    cache_meta_path = internal / 'bsf_model_b1_oof_manifest.json'
    signature = {'method_version': 1, 'model_sha256': file_hash(model_path),
                 'metadata_sha256': file_hash(meta_path), 'csv_sha256': file_hash(raw_path),
                 'scikit_learn_version': sklearn.__version__}
    valid_cache = False
    if cache_path.exists() and cache_meta_path.exists():
        cache_meta = json.loads(cache_meta_path.read_text(encoding='utf-8'))
        valid_cache = cache_meta.get('signature') == signature and cache_meta.get('residuals_sha256') == file_hash(cache_path)
    fold_manifest = []
    if valid_cache:
        oof = pd.read_csv(cache_path)
        fold_manifest = cache_meta['folds']
        fit_count = 0
    else:
        folds = []
        for fold in range(1, 5):
            mask = dev.replicate_id.str.endswith(f'-{fold}')
            train, valid = dev[~mask], dev[mask]
            assert set(train.replicate_id).isdisjoint(valid.replicate_id)
            estimator = clone(model)
            estimator.fit(train[list(FEATURES)], train.target_weight_mg)
            valid = valid.copy()
            valid['predicted_next_weight_mg'] = np.maximum(0, estimator.predict(valid[list(FEATURES)]))
            valid['error_mg'] = valid.predicted_next_weight_mg - valid.target_weight_mg
            valid['fold'] = fold
            valid['data_provenance'] = 'PUBLIC_RESEARCH_DEVELOPMENT_OOF'
            folds.append(valid)
            fold_manifest.append({'fold': fold, 'train_replicates': sorted(train.replicate_id.unique()),
                                  'validation_replicates': sorted(valid.replicate_id.unique()),
                                  'train_rows': len(train), 'validation_rows': len(valid)})
        oof = pd.concat(folds, ignore_index=True)
        oof.to_csv(cache_path, index=False)
        write_json(cache_meta_path, {'signature': signature, 'residuals_sha256': file_hash(cache_path), 'folds': fold_manifest})
        fit_count = 4
    assert len(oof) == 288 and set(oof.replicate_id) == set(dev.replicate_id)
    assert not oof.duplicated(['replicate_id', 'measurement_index_1based']).any()
    assert not set(oof.replicate_id).intersection(test.replicate_id)
    assert np.isfinite(oof.error_mg).all()
    # Descriptive empirical quantile, NOT a conformal coverage guarantee.
    quantile = .90
    radius = float(np.quantile(oof.error_mg.abs(), quantile, method='higher'))
    calibration = {**signature, 'residual_quantile': quantile, 'absolute_error_radius_mg': radius,
                   'n_residuals': len(oof), 'replicate_ids': sorted(oof.replicate_id.unique()),
                   'residuals_sha256': file_hash(cache_path), 'source': 'PUBLIC_RESEARCH_DEVELOPMENT_OOF',
                   'quantile_rule': 'numpy quantile, method=higher, absolute residuals',
                   'nominal_quantile_is_not_individual_confidence': True, 'coverage_guaranteed': False,
                   'limitations': ['Serial dependence within biological replicates.',
                                   'Same development folds were used for hyperparameter selection; optimistic calibration is possible.',
                                   'Fold models fit 12 replicates; final model fit 16; residual distribution may differ.',
                                   'Constant band is a pooled diagnostic, not conditional uncertainty or field validation.']}
    write_json(internal / 'bsf_model_b1_uncertainty.json', calibration)
    predictor = B1Predictor(artifact_root)
    test['predicted_next_weight_mg'] = np.maximum(0, model.predict(test[list(FEATURES)]))
    test['error_mg'] = test.predicted_next_weight_mg - test.target_weight_mg
    test['absolute_error_mg'] = test.error_mg.abs()
    test['lower_mg'] = (test.predicted_next_weight_mg - radius).clip(lower=0)
    test['upper_mg'] = test.predicted_next_weight_mg + radius
    test['covered'] = test.target_weight_mg.between(test.lower_mg, test.upper_mg)
    test['growth_phase'] = phase(test.elapsed_days)
    test['data_provenance'] = 'PUBLIC_RESEARCH_HOLDOUT'
    test['validation_status'] = 'NOT_FIELD_VALIDATED'
    test['model_status'] = 'RESEARCH_PROTOTYPE'
    test['recent_decrease_at_t'] = test.recent_growth_mg_per_day < 0
    test['next_step_decrease_retrospective'] = test.target_weight_mg < test.current_weight_mg
    test['current_weight_bin_mg'] = pd.cut(test.current_weight_mg, [0, 100, 200, 300, np.inf],
                                          labels=['0-100', '100-200', '200-300', '>300']).astype(str)
    test['input_domain_status'] = [predictor.predict(row)['input_domain_status'] for row in records(test[list(FEATURES)])]
    # Anchor to the already published holdout evaluation; never change selection.
    expected_mae = next(m['mae_mg'] for m in original['final_holdout_metrics'] if m['method'] == meta['method'])
    assert abs(test.absolute_error_mg.mean() - expected_mae) < 1e-8
    error_tables = {name: error_table(test, key) for name, key in {
        'moisture': 'moisture_percent', 'phase': 'growth_phase', 'moisture_phase': ['moisture_percent', 'growth_phase'],
        'recent_decrease': 'recent_decrease_at_t', 'next_decrease_retrospective': 'next_step_decrease_retrospective',
        'weight': 'current_weight_bin_mg', 'replicate': 'replicate_id', 'domain': 'input_domain_status',
    }.items()}
    for name, table in error_tables.items():
        table.to_csv(detail / f'bsf_model_b1_errors_by_{name}.csv', index=False)
    test.to_csv(detail / 'bsf_model_b1_holdout_error_analysis.csv', index=False)
    largest = test.nlargest(10, 'absolute_error_mg')
    largest.to_csv(detail / 'bsf_model_b1_largest_errors.csv', index=False)
    oof['covered'] = oof.error_mg.abs() <= radius
    oof_coverage = error_table(oof, 'replicate_id')
    oof_coverage.to_csv(internal / 'bsf_model_b1_oof_coverage_by_replicate.csv', index=False)
    signed_distribution = {str(q): float(test.error_mg.quantile(q)) for q in [0, .05, .25, .5, .75, .95, 1]}

    # Choose by observed holdout absolute error, solely for retrospective illustration.
    eligible = test[test.input_domain_status == 'IN_DOMAIN']
    median = test.absolute_error_mg.median()
    example_indices = {'low_error': eligible.absolute_error_mg.idxmin(),
                       'typical_error': (eligible.absolute_error_mg - median).abs().idxmin(),
                       'difficult_high_error': eligible.absolute_error_mg.idxmax()}
    examples = []
    for label, idx in example_indices.items():
        row = test.loc[idx]
        payload = {key: float(row[key]) for key in FEATURES}
        response = predictor.predict(payload)
        assert abs(response['predicted_next_weight_mg'] - row.predicted_next_weight_mg) < 1e-9
        examples.append({'case': label, 'selection': 'min / nearest full-holdout median / max absolute error among in-domain cases',
                         'data_provenance': 'PUBLIC_RESEARCH_HOLDOUT', 'replicate_id': row.replicate_id,
                         'measurement_index_1based': int(row.measurement_index_1based),
                         'target_elapsed_days': float(row.target_elapsed_days), 'input': payload, 'output': response,
                         'observed_next_weight_mg': float(row.target_weight_mg), 'error_mg': float(row.error_mg),
                         'absolute_error_mg': float(row.absolute_error_mg), 'interval_contains_observation': bool(row.covered)})
    write_json(detail / 'bsf_model_b1_replay_examples.json', examples)
    example_table = pd.DataFrame([{'case': e['case'], 'replicate_id': e['replicate_id'],
                                  'elapsed_days': e['input']['elapsed_days'], 'actual_mg': e['observed_next_weight_mg'],
                                  'predicted_mg': e['output']['predicted_next_weight_mg'], 'absolute_error_mg': e['absolute_error_mg'],
                                  'covered': e['interval_contains_observation']} for e in examples])
    example_table.to_csv(detail / 'bsf_model_b1_replay_examples.csv', index=False)
    late_drops = int((drops.target_elapsed_days > 13).sum())
    summary = {'model_status': 'RESEARCH_PROTOTYPE', 'validation_status': 'NOT_FIELD_VALIDATED',
               'final_estimator_retrained': False, 'validation_fold_fits_this_run': fit_count,
               'protected_sha256': before, 'decreases': {'count': len(drops), 'transitions': len(transitions),
                   'late_target_day_gt13_count': late_drops, 'late_share_of_decreases_pct': 100 * late_drops / len(drops),
                   'by_phase': records(decrease_tables['phase']), 'by_moisture': records(decrease_tables['moisture'])},
               'holdout': error_stats(test), 'holdout_signed_error_quantiles_mg': signed_distribution,
               'uncertainty': calibration, 'by_moisture': records(error_tables['moisture']),
               'by_phase': records(error_tables['phase']), 'by_domain': records(error_tables['domain']),
               'oof_empirical_coverage_pct': float(100 * oof.covered.mean()),
               'oof_replicate_coverage_min_pct': float(oof_coverage.interval_coverage_pct.min()),
               'oof_replicate_coverage_max_pct': float(oof_coverage.interval_coverage_pct.max()),
               'interpretation': 'Post-hoc analysis of a previously inspected holdout; no new independent validation.',
               'integration_decision': 'GO: research replay / contract integration only. NO-GO: field operational decisions.'}
    write_json(detail / 'bsf_model_b1_validation_summary.json', summary)
    report = [
        '# Model B1 — validation & productization',
        '\nRESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED. Sumber: Mendeley DOI 10.17632/k435zc736t.1, CC BY 4.0.',
        '\n## Audit penurunan berat',
        f'\n{len(drops)} dari {len(transitions)} transisi menurun. {late_drops} ({100*late_drops/len(drops):.1f}%) terjadi pada target elapsed day >13.',
        'Fase audit ditentukan pada akhir transisi (target day); early <=6, middle >6 sampai 13, late >13. Rate memakai seluruh transisi dalam kelompok sebagai denominator.',
        md_table(decrease_tables['phase']), md_table(decrease_tables['moisture']),
        'Semua observasi dipertahankan. Ini pola deskriptif dalam 20 replikasi, bukan bukti penyebab biologis. Pengukuran rata-rata, sampling larva, perubahan perkembangan, atau pencatatan memerlukan review ahli; penyebabnya belum dikonfirmasi.',
        '\n## Error model tersimpan',
        '72 pasangan dari 45-5, 55-5, 65-5, 75-5. Bias = prediksi - observasi; positif berarti overprediction. Fase error memakai waktu prediksi t, bukan target day.',
        md_table(error_tables['moisture']), md_table(error_tables['phase']),
        '\nKondisi yang diketahui pada t:', md_table(error_tables['recent_decrease']), md_table(error_tables['weight']),
        '\nPenurunan pada t+1 (analisis retrospektif; tidak tersedia saat inference):', md_table(error_tables['next_decrease_retrospective']),
        '\nSepuluh error terbesar:', md_table(largest[['replicate_id', 'elapsed_days', 'current_weight_mg', 'target_weight_mg', 'predicted_next_weight_mg', 'error_mg']]),
        'Pola pada holdout ini: error lebih besar pada fase tengah/akhir dan setelah penurunan historis; subset berat saat ini >300 mg juga memiliki MAE tinggi tetapi hanya enam sampel. Penurunan pada langkah berikutnya sering di-overpredict. Ini diagnosis retrospektif, bukan pemilihan ulang model atau aturan biologis.',
        '\n## Interval error empiris',
        f'Radius = {radius:.4f} mg, quantile 0.90 (method=higher) dari 288 absolute residual OOF development, 16 replikasi, 4 fold. Tiap fold fit pada 12 replikasi. Interval = [max(0, prediksi-radius), prediksi+radius].',
        f'Cakupan terukur holdout: {int(test.covered.sum())}/{len(test)} ({100*test.covered.mean():.2f}%). Kalibrasi tidak memakai residual holdout atau data sintetis.',
        f'Cakupan OOF per replikasi berkisar {oof_coverage.interval_coverage_pct.min():.1f}% sampai {oof_coverage.interval_coverage_pct.max():.1f}%.',
        'Angka 0.90 adalah quantile residual yang dipilih untuk deskripsi error, bukan peluang kebenaran suatu prediksi. Tidak ada jaminan coverage: residual dalam replikasi berkorelasi, CV juga dipakai untuk pemilihan hiperparameter, dan model fold berbeda ukuran training dengan model final.',
        'Lebar interval tidak dituning terhadap holdout. Holdout sudah pernah ditinjau; analisis ini tidak menciptakan bukti validasi independen baru.',
        '\n## Guardrails dan replay', md_table(error_tables['domain']), md_table(example_table),
        'Input harus enam angka finite dengan unit kontrak. Pelanggaran tipe, kelengkapan, konsistensi, dan domain menghasilkan prediksi null. Domain mengikuti metadata development. Lolos batas marginal tidak menjamin kombinasi fitur, substrat, atau lokasi sesuai studi.',
        'Horizon memakai interval observasi aktual dalam eksperimen; penggunaan mengasumsikan jadwal horizon diketahui pada t. Akurasi tepat 24 jam belum divalidasi terpisah.',
        '\n## Keputusan',
        'GO untuk demo riset dan integrasi kontrak secara offline. NO-GO untuk keputusan operasional farm. Pengumpulan dan evaluasi replikasi lokal independen serta review biologis masih diperlukan.',
        'Estimator final dan raw input tidak diubah. Empat fit tambahan hanya merekonstruksi residual validasi saat cache belum tersedia. Skenario sintetis tetap terpisah dan tidak dihitung dalam evaluasi.',
    ]
    (out / 'bsf_model_b1_validation_report.md').write_text('\n\n'.join(report), encoding='utf-8')
    (detail / 'bsf_model_b1_weight_decrease_report.md').write_text('\n\n'.join(report[:8]), encoding='utf-8')

    fig, axes = plt.subplots(2, 3, figsize=(17, 9))
    pt = decrease_tables['phase'].set_index('phase_at_target').loc[PHASES]
    axes[0, 0].bar(['Early', 'Middle', 'Late'], pt.decrease_rate_pct, color='#387a8c')
    axes[0, 0].set(title='Decrease rate by target-day phase', ylabel='% of all transitions in phase')
    for i, row in enumerate(pt.itertuples()):
        axes[0, 0].text(i, row.decrease_rate_pct + 1, f'{row.decreases}/{row.transitions}', ha='center')
    axes[0, 0].set_ylim(0, 100)
    axes[0, 1].scatter(transitions.target_elapsed_days, transitions.change_mg, s=12,
                        c=np.where(transitions.decrease, '#b7473e', '#387a8c'), alpha=.6)
    axes[0, 1].axhline(0, color='black', lw=.8)
    axes[0, 1].set(title='All 380 measured transitions', xlabel='Target elapsed day', ylabel='Weight change (mg/individual)')
    axes[0, 2].hist(test.error_mg, bins=12, color='#387a8c')
    axes[0, 2].axvline(0, color='black', lw=1)
    axes[0, 2].set(title='72 holdout signed residuals', xlabel='Prediction - actual (mg/individual)', ylabel='Count')
    for moisture, group in test.groupby('moisture_percent'):
        axes[1, 0].scatter(group.elapsed_days, group.error_mg, label=f'{moisture}%', s=22)
    axes[1, 0].axhline(0, color='black', lw=.8)
    axes[1, 0].set(title='Bias patterns across prediction time', xlabel='Elapsed day at t', ylabel='Signed error (mg/individual)')
    axes[1, 0].legend(fontsize=8)
    et = error_tables['phase'].set_index('growth_phase').loc[PHASES]
    x = np.arange(3)
    axes[1, 1].bar(x-.18, et.mae_mg, .36, label='MAE')
    axes[1, 1].bar(x+.18, et.bias_mg, .36, label='Bias')
    axes[1, 1].set_xticks(x, ['Early', 'Middle', 'Late'])
    axes[1, 1].axhline(0, color='black', lw=.8)
    axes[1, 1].set(title='Error by phase at prediction time', ylabel='mg/individual')
    axes[1, 1].legend()
    for i, e in enumerate(examples):
        p = e['output']['predicted_next_weight_mg']
        band = e['output']['uncertainty']
        axes[1, 2].errorbar(i, p, yerr=[[p-band['lower_mg']], [band['upper_mg']-p]], fmt='o', color='#387a8c', capsize=6)
        axes[1, 2].scatter(i, e['observed_next_weight_mg'], color='#b7473e', marker='x', s=70)
    axes[1, 2].set_xticks(range(3), ['Low error', 'Typical', 'Difficult'])
    axes[1, 2].set(title='Blue: prediction + band; red: observed', ylabel='Next wet weight (mg/individual)')
    fig.suptitle('B1 validation | empirical development-residual band | NOT_FIELD_VALIDATED', fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(out / 'bsf_model_b1_validation_visual.png', dpi=160)
    plt.close(fig)
    assert all(file_hash(p) == before[p.name] for p in protected)
    print(json.dumps({'fold_fits': fit_count, 'decreases': summary['decreases'], 'holdout': summary['holdout'],
                      'radius_mg': radius, 'protected_files_unchanged': True}, indent=2))
    return summary


if __name__ == '__main__':
    run_validation()
