from datetime import date, timedelta
from decimal import Decimal
import pytest

from src.domain import (
    Dinero,
    Cantidad,
    NumeroDeLote,
    EstadoDelLote,
    Lote,
    InventarioDeProducto,
    Venta,
    EstadoVenta,
    InvalidDomainData
)

def test_dinero_invalido_negativo():
    #Verifica que no se puedan crear montos de dinero negativos.
    with pytest.raises(InvalidDomainData):
        Dinero(Decimal("-50.00"))


def test_lote_caducado_no_es_vendible():
    #Valida la regla de negocio BR-02: Un lote con fecha vencida no se puede vender.
    hoy = date(2026, 11, 5)
    ayer = hoy - timedelta(days=1)
    
    lote = Lote(
        numero=NumeroDeLote("LOTE-001"),
        caducidad=ayer,
        cantidad=Cantidad(10),
        estado=EstadoDelLote.DISPONIBLE
    )
    
    vendible, motivo = lote.es_vendible(hoy)
    assert vendible is False
    assert "caducado" in motivo.lower()


def test_lote_retirado_no_es_vendible():
    #Valida la regla de negocio BR-03: Un lote marcado como retirado no se puede vender.
    hoy = date(2026, 11, 5)
    mañana = hoy + timedelta(days=1)
    
    lote = Lote(
        numero=NumeroDeLote("LOTE-002"),
        caducidad=mañana,
        cantidad=Cantidad(10),
        estado=EstadoDelLote.RETIRADO
    )
    
    vendible, motivo = lote.es_vendible(hoy)
    assert vendible is False
    assert "retirado" in motivo.lower()


def test_inventario_descuenta_correctamente():
    #Verifica que el inventario controle existencias y descuente de forma adecuada.
    hoy = date(2026, 11, 5)
    mañana = hoy + timedelta(days=1)
    
    lote = Lote(
        numero=NumeroDeLote("LOTE-003"),
        caducidad=mañana,
        cantidad=Cantidad(20),
        estado=EstadoDelLote.DISPONIBLE
    )
    
    inventario = InventarioDeProducto(
        producto_id="PROD-01",
        sucursal_id="SUC-01",
        nivel_minimo=5,
        lotes=[lote]
    )
    
    assert inventario.existencia_total == 20
    assert inventario.esta_por_debajo_del_minimo() is False

    # Descontar 5 unidades
    inventario.verificar_y_descontar("LOTE-003", 5, hoy)
    assert inventario.existencia_total == 15


def test_venta_calcula_total_correctamente():
    """Verifica que una venta calcule el total sumando los subtotales de sus líneas."""
    venta = Venta(
        id="V-001",
        cajero_id="CAJ-01",
        sucursal_id="SUC-01"
    )
    
    # Agregar un producto (ej. 2 unidades a $100.00 c/u)
    venta.agregar_linea(
        producto_id="PROD-01",
        numero_lote=NumeroDeLote("LOTE-003"),
        cantidad=Cantidad(2),
        precio_unitario=Dinero(Decimal("100.00"))
    )
    
    assert venta.total.monto == Decimal("200.00")
    assert venta.estado == EstadoVenta.EN_CAPTURA