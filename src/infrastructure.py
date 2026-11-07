from typing import Optional, Dict, Tuple
from src.domain import Venta, InventarioDeProducto, Dinero
from src.application import (
    RepositorioDeVentas,
    RepositorioDeInventarios,
    ProcesadorDePagos,
    UnidadDeTrabajo
)

class MemoriaRepositorioDeVentas(RepositorioDeVentas):
    #Implementación en memoria del repositorio de ventas para pruebas y ejecución local.
    def __init__(self):
        self.ventas: Dict[str, Venta] = {}

    def obtener_por_id(self, venta_id: str) -> Optional[Venta]:
        return self.ventas.get(venta_id)

    def guardar(self, venta: Venta) -> None:
        self.ventas[venta.id] = venta


class MemoriaRepositorioDeInventarios(RepositorioDeInventarios):
    #Implementación en memoria del inventario de productos por sucursal.
    def __init__(self):
        # La clave es una tupla: (producto_id, sucursal_id)
        self.inventarios: Dict[Tuple[str, str], InventarioDeProducto] = {}

    def obtener_de(self, producto_id: str, sucursal_id: str) -> Optional[InventarioDeProducto]:
        return self.inventarios.get((producto_id, sucursal_id))

    def guardar(self, inventario: InventarioDeProducto) -> None:
        self.inventarios[(inventario.producto_id, inventario.sucursal_id)] = inventario


class SimuladorProcesadorDePagos(ProcesadorDePagos):
    #Adaptador simulado para la pasarela de pagos externo (evita cobros reales).
    def __init__(self, respuesta_exitosa: bool = True):
        self.respuesta_exitosa = respuesta_exitosa

    def cobrar(self, monto: Dinero) -> bool:
        return self.respuesta_exitosa


class MemoriaUnidadDeTrabajo(UnidadDeTrabajo):
    #Simula la Unit of Work (todo o nada) para los agregados.
    def __init__(self):
        self.cometido = False
        self.descartado = False

    def confirmar(self) -> None:
        self.cometido = True

    def descartar(self) -> None:
        self.descartado = True