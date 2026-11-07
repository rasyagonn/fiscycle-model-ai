"""Versioned observation-request rules; no unapproved husbandry thresholds."""
from __future__ import annotations

from app.services.bsf_intelligence import STATUS, timestamp

VERSION = "bsf_dss_observation_v1"

# A catalog of candidate factors, not a list of measured or causal features.
FACTOR_DEFINITIONS = {
    "larval_age_days": ("Umur larva", "hari", "contextual_factor"),
    "a2_estimated_weight_mg": ("Prediksi berat satu larva dari foto", "mg/larva", "model_output"),
    "predicted_next_weight_mg": ("Prediksi berat berikutnya", "mg/larva", "model_output"),
    "forecast_residual_mg": ("Selisih prediksi dengan pengukuran kemudian", "mg/larva", "derived_factor"),
    "observed_mortality_count": ("Kematian larva teramati", "larva", "contextual_factor"),
    "ambient_temperature_c": ("Suhu lingkungan", "C", "contextual_factor"),
    "maintenance_records": ("Riwayat pemeliharaan", None, "contextual_factor"),
    "image_link_verification": ("Kaitan foto dengan batch", None, "rule_factor"),
    "average_weight_mg": ("Rata-rata berat larva terukur", "mg/larva", "measured_input"),
    "weight_change_mg": ("Perubahan berat terukur", "mg/larva", "rule_factor"),
    "cultivation_day": ("Hari pengamatan", "hari", "contextual_factor"),
    "growth_mg_per_day": ("Laju perubahan berat", "mg/larva/hari", "model_feature"),
    "development_stage": ("Tahap perkembangan", None, "contextual_factor"),
    "survival_percent": ("Kelangsungan hidup terukur", "%", "contextual_factor"),
    "visible_count": ("Larva terlihat yang terdeteksi", "larva", "model_output"),
    "moisture_percent": ("Kelembapan substrat", "%", "model_feature"),
    "substrate_temperature_c": ("Suhu substrat", "°C", "contextual_factor"),
    "substrate_type": ("Jenis substrat", None, "contextual_factor"),
    "feed_quantity_g": ("Jumlah pakan", "g", "contextual_factor"),
    "feeding_schedule": ("Jadwal pemberian pakan", None, "contextual_factor"),
    "substrate_replacement": ("Riwayat penggantian substrat", None, "contextual_factor"),
    "substrate_condition": ("Kondisi substrat teramati", None, "contextual_factor"),
    "batch_id": ("ID batch", None, "contextual_factor"),
    "population_estimate": ("Perkiraan populasi independen", "larva", "contextual_factor"),
    "initial_stocking": ("Penebaran awal", "larva", "contextual_factor"),
    "growing_area_m2": ("Luas area tumbuh", "m²", "contextual_factor"),
    "stocking_density": ("Kepadatan tebar", "larva/m²", "contextual_factor"),
    "target_weight_mg": ("Target berat dari operator", "mg/larva", "rule_factor"),
    "planned_harvest_day": ("Rencana hari panen", "hari", "contextual_factor"),
    "observation_recency": ("Waktu pengamatan terakhir", None, "rule_factor"),
    "measurement_source": ("Asal pengukuran", None, "rule_factor"),
    "missing_features": ("Faktor yang belum tersedia", None, "rule_factor"),
    "input_validity": ("Kelayakan input", None, "rule_factor"),
    "history_coverage": ("Jumlah pengamatan", "pengamatan", "rule_factor"),
    "model_version": ("Versi model", None, "rule_factor"),
    "supported_feature_ranges": ("Rentang fitur model", None, "rule_factor"),
    "distribution_shift": ("Kemungkinan perbedaan kondisi data", None, "rule_factor"),
    "camera_compatibility": ("Kesesuaian kamera dan foto", None, "rule_factor"),
    "model_limitations": ("Keterbatasan model", None, "rule_factor"),
    "verified_measurement_availability": ("Ketersediaan pengukuran terverifikasi", None, "rule_factor"),
}

RULES = [
    dict(id="BSF-OBS-001", name="Minta berat terukur", category="growth_monitoring",
         purpose="Dapatkan dasar pengamatan pertumbuhan", required_inputs=[], input_quality="Nilai berat terukur tersedia",
         trigger="Belum ada berat terukur", action="Catat berat rata-rata larva dari pengukuran nyata.",
         explanation="Berat terukur belum tersedia; foto A2 tidak otomatis menjadi rata-rata batch.",
         evidence="Kebutuhan input B1: frozen model metadata", approval_status="OBSERVATION_REQUEST_ONLY", priority="high"),
    dict(id="BSF-OBS-002", name="Periksa penurunan terukur", category="growth_monitoring",
         purpose="Mendeteksi perbedaan pengamatan yang perlu dicek", required_inputs=["average_weight_mg", "weight_change_mg"],
         input_quality="Dua pengukuran berurutan valid", trigger="Berat terakhir lebih kecil daripada sebelumnya",
         action="Ulangi atau periksa pencatatan berat dan kondisi pengukuran.",
         explanation="Selisih dua pengukuran terurut bernilai negatif; penyebab biologis belum diketahui.",
         evidence="Perbandingan aritmetika atas pengukuran yang diberikan", approval_status="OBSERVATION_REQUEST_ONLY", priority="medium"),
    dict(id="BSF-OBS-003", name="Lengkapi kondisi substrat", category="substrate_condition",
         purpose="Menunjukkan data lingkungan yang belum tersedia", required_inputs=["moisture_percent"],
         input_quality="Pengukuran nyata atau metadata penelitian", trigger="Kelembapan tidak diketahui",
         action="Catat kelembapan substrat jika ingin menilai kondisi substrat.",
         explanation="Kondisi substrat belum dapat dinilai karena pengukurannya tidak tersedia.",
         evidence="Kelengkapan data; tanpa batas perlakuan numerik", approval_status="OBSERVATION_REQUEST_ONLY", priority="low"),
    dict(id="BSF-OBS-004", name="Tunda keputusan panen", category="harvest_readiness",
         purpose="Mencegah klaim kesiapan tanpa target dan riwayat", required_inputs=["target_weight_mg", "average_weight_mg", "history_coverage"],
         input_quality="Target operator dan sedikitnya dua pengukuran nyata", trigger="Data target atau tren tidak cukup",
         action="Tetapkan target berat dan ukur perkembangan sebelum menilai panen.",
         explanation="Belum cukup data untuk menilai kesiapan panen.",
         evidence="Prasyarat keputusan operasional; belum disahkan sebagai ambang biologis", approval_status="OBSERVATION_REQUEST_ONLY", priority="medium"),
    dict(id="BSF-OBS-005", name="Tinjau target operator", category="harvest_readiness",
         purpose="Meminta verifikasi saat target operator tercapai", required_inputs=["target_weight_mg", "average_weight_mg", "history_coverage"],
         input_quality="Target operator dan dua pengukuran nyata", trigger="Berat terukur terakhir mencapai target operator",
         action="Periksa sampel baru dan minta keputusan panen dari penanggung jawab.",
         explanation="Target yang ditetapkan operator tercapai pada pengukuran; belum otomatis siap panen.",
         evidence="Perbandingan terhadap target yang diisi operator, bukan ambang ilmiah", approval_status="OBSERVATION_REQUEST_ONLY", priority="medium"),
    dict(id="BSF-OBS-006", name="Periksa kualitas foto", category="image_quality",
         purpose="Menyampaikan batas input model gambar", required_inputs=["camera_compatibility"],
         input_quality="ROI dan protokol foto telah ditinjau", trigger="Kamera atau ROI belum terverifikasi",
         action="Periksa seluruh tubuh larva, penanda, dan kesesuaian kamera; timbang manual bila perlu.",
         explanation="Analisis foto belum memverifikasi kesesuaian kamera, area larva, dan penanda.",
         evidence="Kontrak preprocessing A2 v3 dan laporan validasi pengembangan", approval_status="OBSERVATION_REQUEST_ONLY", priority="medium"),
    dict(id="BSF-OBS-007", name="Periksa cakupan model", category="data_sufficiency",
         purpose="Mencegah penggunaan forecast di luar kontrak", required_inputs=["input_validity"],
         input_quality="Fitur B1 dalam domain", trigger="B1 menolak input sebagai out of domain",
         action="Periksa satuan, waktu, dan kesesuaian data sebelum memakai prediksi.",
         explanation="Fitur tidak sesuai kontrak B1; model tidak menghasilkan forecast yang didukung.",
         evidence="Frozen B1 input validation", approval_status="OBSERVATION_REQUEST_ONLY", priority="high"),
]
for rule in RULES:
    rule["version"] = VERSION
    rule["recommendation_text"] = rule["action"]
    rule["explanation_template"] = rule["explanation"]
    rule["preconditions"] = rule["input_quality"]
    rule["result"] = "Permintaan pengamatan atau verifikasi manusia; tanpa intervensi otomatis"
    rule["limitations"] = "Belum disahkan untuk ambang biologis atau keputusan budidaya otomatis"


FACTOR_CATEGORIES = {
    "biological_growth": {"larval_age_days", "average_weight_mg", "a2_estimated_weight_mg",
        "predicted_next_weight_mg", "forecast_residual_mg", "observed_mortality_count", "weight_change_mg",
        "cultivation_day", "growth_mg_per_day", "development_stage", "survival_percent", "visible_count"},
    "environment_substrate": {"moisture_percent", "substrate_temperature_c", "ambient_temperature_c",
        "substrate_type", "feed_quantity_g", "feeding_schedule", "substrate_replacement",
        "maintenance_records", "substrate_condition"},
    "production": {"batch_id", "population_estimate", "initial_stocking", "growing_area_m2",
        "stocking_density", "target_weight_mg", "planned_harvest_day"},
}


def factor_category(factor_id: str) -> str:
    return next((name for name, keys in FACTOR_CATEGORIES.items() if factor_id in keys), "reliability")


def evaluate_decision(*, observations: list[dict], mode: str, context: dict,
                      forecast: dict | None = None, image_result: dict | None = None) -> dict:
    last = observations[-1] if observations else None
    previous = observations[-2] if len(observations) > 1 else None
    values = dict(context)
    if last:
        values["average_weight_mg"] = last["measured_weight_mg"]
        values["cultivation_day"] = last["day"]
    if previous:
        change = last["measured_weight_mg"] - previous["measured_weight_mg"]
        values["weight_change_mg"] = change
        values["growth_mg_per_day"] = change / (last["day"] - previous["day"])
    if image_result:
        values["visible_count"] = image_result.get("visible_instance_count")
        values["a2_estimated_weight_mg"] = image_result.get("predicted_measured_weight_mg")
        values["camera_compatibility"] = image_result.get("input_quality", "UNVERIFIED")
        values["model_version"] = image_result.get("model_version")
    if forecast:
        values["predicted_next_weight_mg"] = forecast.get("predicted_next_weight_mg")
    values["history_coverage"] = len(observations)
    values["measurement_source"] = mode
    values["observation_recency"] = last.get("day") if last else None
    values["input_validity"] = forecast.get("input_domain_status") if forecast else None
    values["verified_measurement_availability"] = bool(last) and mode != "SIMULATED"
    values["model_limitations"] = "RESEARCH_PROTOTYPE / NOT_FIELD_VALIDATED"
    values["missing_features"] = [key for key in ["average_weight_mg", "moisture_percent", "target_weight_mg"] if values.get(key) is None]
    source = "SIMULATED" if mode == "SIMULATED" else "HISTORICAL_RESEARCH" if mode == "HISTORICAL_RESEARCH" else "USER_ENTERED"
    factors = []
    for factor_id, (name, unit, role) in FACTOR_DEFINITIONS.items():
        value = values.get(factor_id)
        available = value is not None
        if mode == "SIMULATED" and factor_id == "average_weight_mg":
            name = "Berat hipotetis per larva"
        factor_source = source
        if factor_id == "target_weight_mg":
            factor_source = "USER_ENTERED_GOAL" if mode != "SIMULATED" else "SIMULATED"
        elif factor_id in {"visible_count", "camera_compatibility", "a2_estimated_weight_mg"} and image_result:
            factor_source = image_result.get("provenance", "AI_IMAGE_ANALYSIS")
        elif factor_id == "predicted_next_weight_mg" and forecast:
            factor_source = "AI_PREDICTED_B1"
        elif factor_id in {"weight_change_mg", "growth_mg_per_day", "missing_features", "history_coverage", "input_validity"}:
            factor_source = "RULE_DERIVED"
        elif factor_id == "model_version":
            factor_source = "MODEL_ARTIFACT"
        factors.append(dict(factor_id=factor_id, name=name, definition=name, unit=unit, category=factor_category(factor_id),
                            validation_status="NOT_FIELD_VALIDATED" if role == "model_output" else "SOURCE_DEPENDENT",
                            approval_status="CANDIDATE_NOT_APPROVED_FOR_OPERATIONAL_DECISION",
                            current_value=value,
                            availability="AVAILABLE" if available else "MISSING", data_source=factor_source if available else None,
                            reference_range=None, evidence_source="Input/riwayat yang ditampilkan" if available else None,
                            role=role, relationship="conditional" if factor_id in {"target_weight_mg", "weight_change_mg"} else "unknown",
                            assessment="Perlu diperiksa" if available and factor_id == "camera_compatibility" else "Data belum tersedia" if not available else "Tersedia",
                            decision_role="Digunakan bila aturan terkait terpicu" if factor_id in {"average_weight_mg", "weight_change_mg", "target_weight_mg", "moisture_percent", "camera_compatibility", "input_validity"} else "Belum digunakan dalam keputusan ini",
                            last_update=timestamp() if available else None))
    triggered = []
    if last is None:
        triggered.append(RULES[0])
    if previous and values["weight_change_mg"] < 0:
        triggered.append(RULES[1])
    if values.get("moisture_percent") is None:
        triggered.append(RULES[2])
    if last is None or previous is None or values.get("target_weight_mg") is None:
        triggered.append(RULES[3])
    elif last["measured_weight_mg"] >= values["target_weight_mg"] and mode != "SIMULATED":
        triggered.append(RULES[4])
    if image_result and values["camera_compatibility"] != "VERIFIED":
        triggered.append(RULES[5])
    if forecast and forecast.get("input_domain_status") in {"OUT_OF_DOMAIN", "INVALID_INPUT"}:
        triggered.append(RULES[6])
    recommendations = []
    for rule in triggered:
        considered = [f for f in rule["required_inputs"] if values.get(f) is not None]
        missing = [f for f in rule["required_inputs"] if values.get(f) is None]
        recommendations.append(dict(recommendation_id=rule["id"], category=rule["category"], status="review_recommended",
            title=rule["name"], summary=rule["explanation"], observed_condition=rule["trigger"],
            approval_status=rule["approval_status"], limitations=rule["limitations"], observations=observations[-2:],
            factors_considered={key: values[key] for key in considered}, supporting_factors=considered,
            limiting_factors=missing, missing_information=missing, triggered_rule_ids=[rule["id"]],
            evidence_references=[rule["evidence"]], recommended_actions=[rule["action"]],
            requires_human_confirmation=True, data_quality_status="EXPERIMENTAL",
            model_versions={"b1": "frozen_v1"} if forecast else {}, rule_version=VERSION,
            generated_at=timestamp(), provenance="RULE_DERIVED"))
    return {"assessment": "Belum cukup data untuk keputusan operasional otomatis." if not recommendations else "Ada pengamatan yang perlu ditinjau.",
            "decision_status": "ABSTAIN_OPERATIONAL",
            "recommendations": recommendations, "factors": factors, "missing_information": values["missing_features"],
            "triggered_rule_ids": [r["id"] for r in triggered], "rule_version": VERSION,
            "data_mode": mode, "status": STATUS, "generated_at": timestamp(),
            "explanation": "Aturan hanya meminta verifikasi dan pengamatan; tidak ada ambang perlakuan substrat atau keputusan panen otomatis."}
