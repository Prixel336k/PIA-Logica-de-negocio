from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)


def test_api_get_venta_existente():
    #Verifica que la API devuelva los detalles de una venta existente (200 OK).
    response = client.get("/orders/V-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "V-001"
    assert data["estado"] == "EN_CAPTURA"


def test_api_get_venta_no_encontrada():
    #Verifica el manejo del error 404 cuando la venta no existe.
    response = client.get("/orders/V-999")
    assert response.status_code == 404
    assert "no se encuentra registrada" in response.json()["detail"]


def test_api_consultar_inventario():
    #Verifica el endpoint de consulta de inventario por sucursal.
    response = client.get("/inventarios/PROD-01/SUC-01")
    assert response.status_code == 200
    data = response.json()
    assert "informacion" in data


def test_api_agregar_linea_error_422():
    #Verifica que al enviar una cantidad inválida salte el error 422.
    payload = {
        "producto_id": "PROD-01",
        "numero_lote": "LOTE-100",
        "cantidad": -5,
        "precio_unitario": 100.0
    }
    response = client.post("/orders/V-001/lineas", json=payload)
    assert response.status_code == 422