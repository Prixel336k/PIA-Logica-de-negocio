from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)


def test_api_get_venta_existente():
    # Verifica que la API devuelva los detalles de una venta existente (200 OK).
    client.post("/demo/reiniciar")
    response = client.get("/orders/V-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "V-001"
    assert data["estado"] == "EN_CAPTURA"


def test_api_get_venta_no_encontrada():
    # Verifica el manejo del error 404 cuando la venta no existe.
    response = client.get("/orders/V-999")
    assert response.status_code == 404
    assert "no se encuentra registrada" in response.json()["detail"]


def test_api_consultar_inventario():
    # Verifica el endpoint de consulta de inventario por sucursal.
    response = client.get("/inventarios/PROD-01/SUC-01")
    assert response.status_code == 200
    data = response.json()
    assert "informacion" in data


def test_api_agregar_linea_error_422():
    # Verifica que al enviar una cantidad inválida salte el error 422.
    payload = {
        "producto_id": "PROD-01",
        "numero_lote": "LOTE-100",
        "cantidad": -5,
        "precio_unitario": 100.0,
    }
    response = client.post("/orders/V-001/lineas", json=payload)
    assert response.status_code == 422


def test_api_interfaz_web_y_contexto():
    # Verifica que la interfaz HTML/CSS y los endpoints de sistema funcionen.
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "FarmaExpress" in res_home.text

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    res_ctx = client.get("/contexto-demo")
    assert res_ctx.status_code == 200
    assert len(res_ctx.json()["productos"]) >= 6


def test_api_validacion_especial_y_restriccion_rol_403():
    # Verifica US-03, BR-04 y BR-05 (422 al intentar cobrar sin validar, 403 si cajero intenta validar, 200 con responsable_farmacia)
    client.post("/demo/reiniciar")

    # V-002 tiene Amoxicilina pendiente de validación -> no debe dejar cobrar (422)
    res_cobro_bloqueado = client.post("/orders/V-002/completar")
    assert res_cobro_bloqueado.status_code == 422
    assert "BR-04" in res_cobro_bloqueado.json()["detail"]

    # Cajero intenta aprobar validación -> 403 Forbidden (BR-05)
    res_cajero = client.post(
        "/orders/V-002/validaciones",
        json={
            "linea_o_producto_id": "PROD-02",
            "aprueba": True,
            "responsable_id": "CAJ-01",
            "rol_usuario": "cajero",
        },
    )
    assert res_cajero.status_code == 403

    # Responsable de farmacia aprueba -> 200 OK y luego se puede cobrar -> 200 OK
    res_farm = client.post(
        "/orders/V-002/validaciones",
        json={
            "linea_o_producto_id": "PROD-02",
            "aprueba": True,
            "responsable_id": "FARM-01",
            "rol_usuario": "responsable_farmacia",
        },
    )
    assert res_farm.status_code == 200

    res_cobro_ok = client.post("/orders/V-002/completar")
    assert res_cobro_ok.status_code == 200
    assert res_cobro_ok.json()["estado_actual"] == "COMPLETADA"

    # Intentar volver a cobrar una venta ya completada -> 409 Conflict
    res_conflicto = client.post("/orders/V-002/completar")
    assert res_conflicto.status_code == 409


def test_api_sustituciones_almacen_compras_e_indicadores():
    client.post("/demo/reiniciar")

    # 1. Flujo de sustitución (US-07, US-08, BR-08)
    res_alt = client.get("/productos/PROD-06/alternativas/SUC-01")
    assert res_alt.status_code == 200

    res_val_sust = client.post(
        "/sustituciones/SUST-001/validar",
        json={
            "alternativa_id": "PROD-05",
            "aprueba": True,
            "responsable_id": "FARM-01",
            "rol_usuario": "responsable_farmacia",
        },
    )
    assert res_val_sust.status_code == 200

    res_dec_cli = client.post("/sustituciones/SUST-001/decision-cliente", json={"acepta": True})
    assert res_dec_cli.status_code == 200
    assert res_dec_cli.json()["estado"] == "ACEPTADA_POR_CLIENTE"

    # 2. Recepción en almacén y restricción BR-14 al cajero (US-14)
    res_rec_cajero = client.post(
        "/recepciones",
        json={
            "sucursal_id": "SUC-01",
            "producto_id": "PROD-01",
            "numero_lote": "LOTE-900",
            "caducidad": "2027-12-01",
            "cantidad": 10,
            "responsable": "CAJ-01",
            "rol_usuario": "cajero",
        },
    )
    assert res_rec_cajero.status_code == 403

    res_rec_alm = client.post(
        "/recepciones",
        json={
            "sucursal_id": "SUC-01",
            "producto_id": "PROD-01",
            "numero_lote": "LOTE-900",
            "caducidad": "2027-12-01",
            "cantidad": 10,
            "responsable": "ALM-01",
            "rol_usuario": "almacen",
        },
    )
    assert res_rec_alm.status_code == 201

    # 3. Diferencias de inventario (US-10, BR-13, RF-15)
    res_rev_dif = client.post(
        "/diferencias-inventario/DIF-001/revisar",
        json={
            "aprobar_ajuste": True,
            "revisado_por": "FARM-01",
            "rol_usuario": "responsable_farmacia",
            "observacion": "Ajuste confirmado por supervisión",
        },
    )
    assert res_rev_dif.status_code == 200

    # 4. Análisis de resurtido por Compras (US-12, BR-10)
    res_comp = client.post(
        "/resurtidos/RES-001/analizar",
        json={
            "solicitar_abastecimiento": True,
            "analizado_por": "COMP-01",
            "rol_usuario": "compras",
            "cantidad_solicitada": 30,
            "justificacion": "Reposición autorizada por Compras",
        },
    )
    assert res_comp.status_code == 200

    # 5. Disponibilidad multisucursal, indicadores, políticas y bitácora (US-13, US-16, BR-12)
    assert client.get("/disponibilidad-sucursales/PROD-06").status_code == 200
    assert client.get("/inventarios-sucursal/SUC-01").status_code == 200
    assert client.get("/orders").status_code == 200
    assert client.get("/validaciones-pendientes").status_code == 200
    assert client.get("/sustituciones").status_code == 200
    assert client.get("/recepciones").status_code == 200
    assert client.get("/diferencias-inventario").status_code == 200
    assert client.get("/resurtidos").status_code == 200
    assert client.get("/indicadores").status_code == 200
    assert client.post("/politicas/caducidad", json={"dias_proximidad_caducidad": 45, "rol_usuario": "administracion"}).status_code == 200
    assert client.get("/bitacora-eventos").status_code == 200

    # 6. Iniciar nueva venta, agregar por FEFO, retirar lote y registrar nueva diferencia y sustitución
    assert client.post("/orders", json={"venta_id": "V-010", "cajero_id": "CAJ-01", "sucursal_id": "SUC-01"}).status_code == 201
    assert client.post(
        "/orders/V-010/lineas",
        json={"producto_id": "PROD-01", "cantidad": 1, "validar_en_inventario": True},
    ).status_code == 200
    assert client.post(
        "/sustituciones",
        json={"venta_id": "V-010", "producto_original_id": "PROD-06", "cantidad": 1},
    ).status_code == 201
    assert client.post(
        "/lotes/retirar",
        json={
            "producto_id": "PROD-02",
            "sucursal_id": "SUC-01",
            "numero_lote": "LOTE-PROX-201",
            "responsable": "FARM-01",
            "rol_usuario": "responsable_farmacia",
            "motivo": "Retiro preventivo de prueba",
        },
    ).status_code == 200
    assert client.post(
        "/diferencias-inventario",
        json={
            "producto_id": "PROD-01",
            "sucursal_id": "SUC-01",
            "numero_lote": "LOTE-100",
            "cantidad_fisica": 17,
            "motivo": "Conteo cíclico",
            "reportado_por": "ALM-01",
            "rol_usuario": "almacen",
        },
    ).status_code == 201

    client.post("/demo/reiniciar")
