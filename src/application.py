from typing import Protocol, Optional
from datetime import date
from src.domain import Venta, InventarioDeProducto, Dinero, Cantidad

#Puertos / Interfaces de Infraestructura (ADR-005)
class RepositorioDeVentas(Protocol):
    def obtener_por_id(self, venta_id: str) -> Optional[Venta]: ...
    def guardar(self, venta: Venta) -> None: ...


class RepositorioDeInventarios(Protocol):
    def obtener_de(self, producto_id: str, sucursal_id: str) -> Optional[InventarioDeProducto]: ...
    def guardar(self, inventario: InventarioDeProducto) -> None: ...


class ProcesadorDePagos(Protocol):
    def cobrar(self, monto: Dinero) -> bool: ...


class UnidadDeTrabajo(Protocol):
    def confirmar(self) -> None: ...
    def descartar(self) -> None: ...


#Casos de Uso / Commands (ADR-003)
class CompletarVentaService:
    """
    Orquesta el caso de uso CU-04: Completar venta y actualizar inventario.
    Sigue estrictamente el orden de cobro: verifica -> procesa pago -> descuenta inventario -> confirma (ADR-004).
    """
    def __init__(
        self,
        ventas_repo: RepositorioDeVentas,
        inventarios_repo: RepositorioDeInventarios,
        procesador_pagos: ProcesadorDePagos,
        uow: UnidadDeTrabajo
    ):
        self.ventas_repo = ventas_repo
        self.inventarios_repo = inventarios_repo
        self.procesador_pagos = procesador_pagos
        self.uow = uow

    def ejecutar(self, venta_id: str, hoy: date) -> str:
        venta = self.ventas_repo.obtener_por_id(venta_id)
        if not venta:
            raise ValueError("La venta especificada no existe.")

        # 1. Verificar si la venta puede cobrarse (valida recetas o requisitos especiales)
        venta.puede_cobrarse()

        # 2. Verificar la disponibilidad y vendibilidad de cada línea antes de tocar dinero o inventario
        for linea in venta.lineas:
            inv = self.inventarios_repo.obtener_de(linea.producto_id, venta.sucursal_id)
            if not inv:
                raise ValueError(f"No hay inventario para el producto {linea.producto_id} en la sucursal {venta.sucursal_id}.")
            
            lote_obj = next((l for l in inv.lotes if l.numero.codigo == linea.numero_lote.codigo), None)
            if not lote_obj:
                raise ValueError(f"El lote {linea.numero_lote.codigo} no se encuentra registrado.")
            
            vendible, motivo = lote_obj.es_vendible(hoy)
            if not vendible:
                raise ValueError(f"Lote no vendible: {motivo}")
            
            if lote_obj.cantidad.valor < linea.cantidad.valor:
                raise ValueError(f"Existencia insuficiente en el lote {linea.numero_lote.codigo}.")

        # 3. Procesar el pago con la pasarela externa
        pago_exitoso = self.procesador_pagos.cobrar(venta.total)
        if not pago_exitoso:
            venta.rechazar("Pago rechazado por el procesador.")
            self.ventas_repo.guardar(venta)
            self.uow.confirmar()
            raise RuntimeError("El pago fue rechazado. La venta se marcó como rechazada y el inventario no se afectó.")

        # 4. Descontar inventarios y completar venta
        for linea in venta.lineas:
            inv = self.inventarios_repo.obtener_de(linea.producto_id, venta.sucursal_id)
            inv.verificar_y_descontar(linea.numero_lote.codigo, linea.cantidad.valor, hoy)
            self.inventarios_repo.guardar(inv)

        venta.completar()
        self.ventas_repo.guardar(venta)
        self.uow.confirmar()

        return "Venta completada y registrada exitosamente."


#Queries / Consultas (CQRS Básico - ADR-003)
class ConsultarDisponibilidadQuery:
#Servicio de consulta pura (Query) que lee el estado del inventario sin cargar agregados de escritura.
    def __init__(self, inventarios_repo: RepositorioDeInventarios):
        self.inventarios_repo = inventarios_repo

    def ejecutar(self, producto_id: str, sucursal_id: str) -> dict:
        inv = self.inventarios_repo.obtener_de(producto_id, sucursal_id)
        if not inv:
            return {
                "producto_id": producto_id,
                "sucursal_id": sucursal_id,
                "existencia_total": 0,
                "alerta_minimo": False,
                "lotes": []
            }
        
        return {
            "producto_id": inv.producto_id,
            "sucursal_id": inv.sucursal_id,
            "existencia_total": inv.existencia_total,
            "alerta_minimo": inv.esta_por_debajo_del_minimo(),
            "lotes": [
                {
                    "numero": l.numero.codigo,
                    "cantidad": l.cantidad.valor,
                    "caducidad": str(l.caducidad),
                    "estado": l.estado.value
                } 
                for l in inv.lotes
            ]
        }