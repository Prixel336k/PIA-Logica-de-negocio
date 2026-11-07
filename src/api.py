from fastapi import FastAPI, HTTPException
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field

from src.domain import (
    Dinero,
    Cantidad,
    NumeroDeLote,
    EstadoDelLote,
    Lote,
    InventarioDeProducto,
    Venta,
    InvalidDomainData,
    InvalidOrderTransition
)
from src.application import (
    CompletarVentaService,
    ConsultarDisponibilidadQuery
)
from src.infrastructure import (
    MemoriaRepositorioDeVentas,
    MemoriaRepositorioDeInventarios,
    SimuladorProcesadorDePagos,
    MemoriaUnidadDeTrabajo
)

app = FastAPI(
    title="FarmaExpress API"
)

#Repositorios en memoria compartidos
ventas_repo = MemoriaRepositorioDeVentas()
inventarios_repo = MemoriaRepositorioDeInventarios()

#Precarga de datos iniciales para demostración
def _inicializar_datos_mock():
    lote = Lote(
        numero=NumeroDeLote("LOTE-100"),
        caducidad=date(2027, 6, 1),
        cantidad=Cantidad(20),
        estado=EstadoDelLote.DISPONIBLE
    )
    inventario = InventarioDeProducto(
        producto_id="PROD-01",
        sucursal_id="SUC-01",
        nivel_minimo=5,
        lotes=[lote]
    )
    inventarios_repo.guardar(inventario)

    venta = Venta(
        id="V-001",
        cajero_id="CAJ-01",
        sucursal_id="SUC-01"
    )
    venta.agregar_linea(
        producto_id="PROD-01",
        numero_lote=NumeroDeLote("LOTE-100"),
        cantidad=Cantidad(2),
        precio_unitario=Dinero(Decimal("250.00"))
    )
    ventas_repo.guardar(venta)

_inicializar_datos_mock()


#Funciones de apoyo
def get_venta_or_404(venta_id: str) -> Venta:
    #Busca la venta o lanza un error 404(que seria que la venta no se encuentra).
    venta = ventas_repo.obtener_por_id(venta_id)
    if venta is None:
        raise HTTPException(
            status_code=404, 
            detail="Lo sentimos, la venta solicitada no se encuentra registrada en el sistema."
        )
    return venta


def run_action(venta, action):
    #Ejecuta una acción de negocio dando respuestas claras
    try:
        action()
        # Guarda el estado actualizado en el repositorio tras la acción exitosa
        ventas_repo.guardar(venta)
    except InvalidOrderTransition as exc:
        raise HTTPException(
            status_code=409, 
            detail=f"Atención: No se pudo completar la operación debido al estado actual de la venta: {str(exc)}"
        )
    except (InvalidDomainData, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=422, 
            detail=f"Error de validación en las reglas de negocio farmacéutico: {str(exc)}"
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    
    return {
        "mensaje_para_cliente": "Su orden ha sido procesada y confirmada exitosamente.",
        "venta_id": venta.id,
        "estado_actual": venta.estado.value,
        "total": str(venta.total.monto)
    }


#Endpoints
@app.get("/orders/{venta_id}", summary="Consultar detalles de una venta")
def get_order_details(venta_id: str):
    #Devuelve la información detallada de la venta para que se visualice.
    venta = get_venta_or_404(venta_id)
    return {
        "id": venta.id,
        "cajero_id": venta.cajero_id,
        "sucursal_id": venta.sucursal_id,
        "estado": venta.estado.value,
        "total": str(venta.total.monto),
        "moneda": "MXN",
        "lineas": [
            {
                "producto_id": l.producto_id,
                "lote": l.numero_lote.codigo,
                "cantidad": l.cantidad.valor,
                "precio_unitario": str(l.precio_unitario.monto),
                "subtotal": str(l.subtotal.monto),
                "validacion": l.validacion.value
            }
            for l in venta.lineas
        ],
        "eventos": [e.nombre for e in venta.eventos]
    }


@app.post("/orders/{venta_id}/completar", summary="Completar y cobrar una venta de forma segura")
def completar_venta_endpoint(venta_id: str):
    
    #Ejecuta el caso de uso CU-04 utilizando el servicio de aplicación dentro de la función de apoyo unificada.
    venta = get_venta_or_404(venta_id)
    
    procesador_pagos = SimuladorProcesadorDePagos(respuesta_exitosa=True)
    uow = MemoriaUnidadDeTrabajo()
    
    servicio = CompletarVentaService(
        ventas_repo=ventas_repo,
        inventarios_repo=inventarios_repo,
        procesador_pagos=procesador_pagos,
        uow=uow
    )
    
    return run_action(venta, lambda: servicio.ejecutar(venta_id, date.today()))


@app.get("/inventarios/{producto_id}/{sucursal_id}", summary="Consultar disponibilidad por sucursal")
def consultar_inventario_endpoint(producto_id: str, sucursal_id: str):
    #Consulta de inventario por sucursal.
    query = ConsultarDisponibilidadQuery(inventarios_repo)
    resultado = query.ejecutar(producto_id, sucursal_id)
    return {
        "mensaje": "Consulta realizada correctamente.",
        "informacion": resultado
    }


#Esquema para recibir datos de una nueva línea de venta
class AgregarLineaRequest(BaseModel):
    producto_id: str = Field(..., json_schema_extra={"example": "PROD-01"})
    numero_lote: str = Field(..., json_schema_extra={"example": "LOTE-100"})
    cantidad: int = Field(..., json_schema_extra={"example": -5})
    precio_unitario: float = Field(..., json_schema_extra={"example": 100.0})

@app.post("/orders/{venta_id}/lineas", summary="Agregar producto a la venta")
def agregar_linea_endpoint(venta_id: str, body: AgregarLineaRequest):
    #Permite agregar una línea validando las reglas del dominio.
    venta = get_venta_or_404(venta_id)
    
    return run_action(venta, lambda: venta.agregar_linea(
        producto_id=body.producto_id,
        numero_lote=NumeroDeLote(body.numero_lote),
        cantidad=Cantidad(body.cantidad),
        precio_unitario=Dinero(Decimal(str(body.precio_unitario)))
    ))