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
    EstadoVenta
)
from src.application import CompletarVentaService
from src.infrastructure import (
    MemoriaRepositorioDeVentas,
    MemoriaRepositorioDeInventarios,
    SimuladorProcesadorDePagos,
    MemoriaUnidadDeTrabajo
)


def test_completar_venta_exitososa():
    #Valida el flujo completo del caso de uso CU-04: venta cobrada, inventario descontado y venta completada.
    hoy = date(2026, 11, 5)
    mañana = hoy + timedelta(days=1)
    
    #1. Preparar infraestructura y repositorios en memoria
    ventas_repo = MemoriaRepositorioDeVentas()
    inventarios_repo = MemoriaRepositorioDeInventarios()
    procesador_pagos = SimuladorProcesadorDePagos(respuesta_exitosa=True)
    uow = MemoriaUnidadDeTrabajo()
    
    #2. Configurar inventario inicial con un lote válido
    lote = Lote(
        numero=NumeroDeLote("LOTE-100"),
        caducidad=mañana,
        cantidad=Cantidad(10),
        estado=EstadoDelLote.DISPONIBLE
    )
    inventario = InventarioDeProducto(
        producto_id="PROD-99",
        sucursal_id="SUC-01",
        nivel_minimo=2,
        lotes=[lote]
    )
    inventarios_repo.guardar(inventario)
    
    #3. Crear una venta en captura
    venta = Venta(
        id="V-100",
        cajero_id="CAJ-01",
        sucursal_id="SUC-01"
    )
    venta.agregar_linea(
        producto_id="PROD-99",
        numero_lote=NumeroDeLote("LOTE-100"),
        cantidad=Cantidad(2),
        precio_unitario=Dinero(Decimal("150.00"))
    )
    ventas_repo.guardar(venta)
    
    #4. Ejecutar el servicio de aplicación
    servicio = CompletarVentaService(
        ventas_repo=ventas_repo,
        inventarios_repo=inventarios_repo,
        procesador_pagos=procesador_pagos,
        uow=uow
    )
    
    resultado = servicio.ejecutar("V-100", hoy)
    
    #5. Verificaciones
    assert "exitosamente" in resultado
    assert venta.estado == EstadoVenta.COMPLETADA
    assert inventario.existencia_total == 8  # Tenía 10, se vendieron 2
    assert uow.cometido is True