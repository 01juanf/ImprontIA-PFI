"""Fase 2, P03: kit de simulación (etiqueta oculta, exportación y análisis)."""
import csv
import math
import typing

import numpy as np
import pytest
from sqlalchemy import create_engine, inspect

from app import schemas
from app.database import SessionLocal
from app.db_migrations import HEAD_REVISION, current_revision, downgrade_db, upgrade_db
from app.evaluation.metrics import far_frr
from app.evaluation.reales import analizar, registros_desde_sesiones
from app.evaluation.synthetic import SyntheticParams, generate_session
from app.processing.features import compute_all_features
from app.processing.pipeline import evaluate_session
from app.processing.anomaly import fit_population_model
from app.simulacion import CONDICIONES
from scripts.analizar_reales import leer_csv, reporte_md
from scripts.exportar_sesiones import cargar_sesiones, escribir_csv


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


EVENTOS = [{"t": 0, "type": "keydown"}, {"t": 90, "type": "keyup"},
           {"t": 200, "type": "keydown"}, {"t": 300, "type": "keyup"},
           {"t": 400, "type": "paste", "chars": 800}]


def _exam(client, token, name):
    r = client.post("/exams", headers=auth_headers(token), json={
        "name": name, "prompt_text": "Consigna", "info_text": "info", "rules_text": "reglas",
        "allowed_signals": ["keyboard", "mouse", "focus", "clipboard"]})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _session(client, exam, participant, condicion=None, eventos=EVENTOS):
    body = {"exam_code": exam["join_code"], "participant_id": participant, "consent_given": True, "context": {}}
    if condicion is not None:
        body["condicion_simulacion"] = condicion
    s = client.post("/sessions/start", json=body)
    assert s.status_code == 200, s.text
    s = s.json()
    h = {"X-Session-Token": s["session_token"]}
    client.post(f"/sessions/{s['session_id']}/events", headers=h, json={"seq": 1, "events": eventos})
    client.post(f"/sessions/{s['session_id']}/end", headers=h)
    return s["session_id"]


def test_condiciones_coinciden_con_el_esquema():
    hint = typing.get_type_hints(schemas.SessionStartRequest)["condicion_simulacion"]
    literal = [a for a in typing.get_args(hint) if a is not type(None)][0]
    assert typing.get_args(literal) == CONDICIONES


def test_etiqueta_se_guarda_oculta_y_no_cambia_el_procesamiento(client, teacher_token):
    exam = _exam(client, teacher_token, "Simulación oculta")
    sin = _session(client, exam, "SIM-A")
    con = _session(client, exam, "SIM-B", "pegado")

    db = SessionLocal()
    from app import models
    assert db.get(models.Session, sin).condicion_simulacion is None
    assert db.get(models.Session, con).condicion_simulacion == "pegado"
    db.close()

    # El docente no la ve en ninguna respuesta.
    for sid in (sin, con):
        detalle = client.get(f"/sessions/{sid}", headers=auth_headers(teacher_token))
        assert "\"pegado\"" not in detalle.text and "condicion" not in detalle.text
    lista = client.get(f"/sessions?exam_id={exam['id']}", headers=auth_headers(teacher_token))
    assert lista.status_code == 200 and "condicion" not in lista.text
    pan = client.get(f"/exams/{exam['id']}/panorama", headers=auth_headers(teacher_token))
    assert "condicion" not in pan.text

    # Mismos eventos, misma salida del pipeline con y sin etiqueta.
    a = client.get(f"/sessions/{sin}", headers=auth_headers(teacher_token)).json()
    b = client.get(f"/sessions/{con}", headers=auth_headers(teacher_token)).json()
    assert a["needs_review"] == b["needs_review"] is True
    assert sorted(i["kind"] for i in a["indicators"]) == sorted(i["kind"] for i in b["indicators"])
    assert {m["name"]: m["value"] for m in a["metrics"]} == {m["name"]: m["value"] for m in b["metrics"]}

    # Valor desconocido: 422.
    r = client.post("/sessions/start", json={"exam_code": exam["join_code"], "participant_id": "X",
                                             "consent_given": True, "condicion_simulacion": "trampa"})
    assert r.status_code == 422


def test_registros_sin_datos_personales_y_solo_etiquetados():
    base = {"exam_id": "uuid-exam", "needs_review": False, "indicadores": [], "n_eventos": 10, "duracion_s": 60.04,
            "metricas": {"mean_dwell_time_ms": 90.0}}
    sesiones = [
        {**base, "participant_id": "martina.h", "condicion": "normal"},
        {**base, "participant_id": "juan.f", "condicion": None},
        {**base, "participant_id": "juan.f", "condicion": "pegado", "needs_review": True,
         "indicadores": [("paste_volume_alto", "medium")]},
        {**base, "participant_id": "martina.h", "condicion": "consulta_externa",
         "indicadores": [("cambios_pestana_frecuentes", "low")]},  # permitida por las reglas: no cuenta
    ]
    filas = registros_desde_sesiones(sesiones)
    assert [f["participante"] for f in filas] == ["P01", "P02", "P01"]
    assert [f["y_true"] for f in filas] == [0, 1, 1]
    assert [f["marcada_reglas"] for f in filas] == [0, 1, 0]
    assert [f["orden_participante"] for f in filas] == [1, 1, 2]
    texto = repr(filas)
    assert "martina" not in texto and "juan" not in texto and "uuid-exam" not in texto
    assert len(registros_desde_sesiones(sesiones, incluir_sin_etiqueta=True)) == 4


def _filas_sinteticas(n_normales=30, por_condicion=6, seed=7):
    """Sesiones sintéticas etiquetadas como si fueran simulaciones (2 participantes)."""
    rng = np.random.default_rng(seed)
    params = SyntheticParams()
    perfiles = {"pegado": "pegado_masivo", "consulta_externa": "cambio_pestana", "transcripcion": "tecleo_automatizado",
                "suplantacion": "ritmo_distinto"}
    pop = fit_population_model([compute_all_features(generate_session(rng, params, "normal")) for _ in range(24)])
    sesiones = []
    plan = [("normal", "normal")] * n_normales + [(c, p) for c, p in perfiles.items() for _ in range(por_condicion)]
    for i, (cond, perfil) in enumerate(plan):
        feats = compute_all_features(generate_session(rng, params, perfil))
        out = evaluate_session(feats, pop)
        sesiones.append({"exam_id": "e", "participant_id": f"p{i % 2}", "condicion": cond,
                         "needs_review": out.needs_review, "indicadores": [(d.kind, getattr(d.level, "value", d.level)) for d in out.drafts],
                         "metricas": feats, "n_eventos": 0, "duracion_s": 0})
    return registros_desde_sesiones(sesiones)


def test_analizar_usa_las_metricas_de_la_evaluacion():
    filas = _filas_sinteticas()
    res = analizar(filas, n_boot=50)
    op = res["global"]["operacion"]
    assert op == far_frr([f["y_true"] for f in filas], [f["marcada"] for f in filas])
    assert res["global"]["n"] == 54 and res["participantes"] == 2
    assert res["global"]["modelo_score"]["n_con_score"] == 54  # 29 normales para cada normal dejada afuera
    # Suplantación (otro ritmo, 2σ en 3 rasgos) es lo que el modelo poblacional puede separar;
    # pegado / transcripción / consulta los detectan las reglas (como en el Incremento 6).
    assert res["por_condicion"]["suplantacion"]["modelo_score"]["auc_roc"] > 0.8
    for c in ("pegado", "transcripcion", "consulta_externa"):
        assert res["por_condicion"][c]["detectadas_reglas"] == 6
    assert set(res["intervalos"]) == {"far", "frr", "auc_roc", "average_precision", "eer"}
    assert any("participante(s)" in a for a in res["avisos"])
    assert "## Por condición" in reporte_md(res, "x.csv")
    # Reproducible con la misma semilla.
    assert analizar(filas, n_boot=50)["intervalos"] == res["intervalos"]


def test_analizar_sin_poblacion_suficiente_o_por_participante():
    filas = _filas_sinteticas(n_normales=12, por_condicion=2)
    res = analizar(filas, n_boot=0)
    assert all(math.isnan(s) for s in res["scores"])
    assert math.isnan(res["global"]["modelo_score"]["auc_roc"])
    assert any("al menos 21" in a for a in res["avisos"])

    filas = _filas_sinteticas(n_normales=44, por_condicion=2)
    res = analizar(filas, excluir_participante=True, n_boot=0)
    # 22 normales por persona: cada sesión se puntúa con las 22 de la otra.
    assert not any(math.isnan(s) for s in res["scores"])
    assert any("Partición por participante" in a for a in res["avisos"])


def test_exportar_y_analizar_de_punta_a_punta(client, teacher_token, tmp_path):
    exam = _exam(client, teacher_token, "Simulación export")
    _session(client, exam, "MARTINA-01", "normal", EVENTOS[:4])
    _session(client, exam, "JUAN-02", "pegado")
    _session(client, exam, "JUAN-02")  # sin etiqueta: no se exporta
    db = SessionLocal()
    try:
        sesiones = cargar_sesiones(db, [exam["join_code"].lower()])
    finally:
        db.close()
    assert len(sesiones) == 3
    destino = tmp_path / "sim.csv"
    escribir_csv(registros_desde_sesiones(sesiones), destino)
    contenido = destino.read_text(encoding="utf-8")
    assert "MARTINA" not in contenido and "JUAN" not in contenido and exam["id"] not in contenido
    filas = leer_csv(destino)
    assert [(f["participante"], f["condicion"], f["marcada"]) for f in filas] == [("P01", "normal", "0"), ("P02", "pegado", "1")]
    assert "paste_chars_total" in filas[0]
    res = analizar(filas, n_boot=0)
    assert res["global"]["operacion"]["far"] == 0.0 and res["global"]["operacion"]["frr"] == 0.0


def test_migracion_0003_sube_y_baja(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    upgrade_db(eng)
    assert current_revision(eng) == HEAD_REVISION
    assert "condicion_simulacion" in {c["name"] for c in inspect(eng).get_columns("sessions")}
    downgrade_db(eng, "0002_campos_er")
    assert "condicion_simulacion" not in {c["name"] for c in inspect(eng).get_columns("sessions")}
    upgrade_db(eng)
    assert current_revision(eng) == HEAD_REVISION
    eng.dispose()
