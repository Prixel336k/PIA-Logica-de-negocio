from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from enum import Enum
from typing import List

#Excepciones de Dominio
class DomainException(Exception):
    pass

class InvalidDomainData(DomainException):
    pass

class InvalidOrderTransition(DomainException):
    pass

#Value Objects
@dataclass(frozen=True)
class Dinero:
    monto: Decimal
    moneda: str = "MXN"

    def __post_init__(self):
        if not self.monto.is_finite() or self.monto < 0:
            raise InvalidDomainData("El monto de dinero no puede ser negativo o no finito.")

    def sumar(self, otro: 'Dinero') -> 'Dinero':
        if self.moneda != otro.moneda:
            raise InvalidDomainData("No se pueden sumar montos de diferentes monedas.")
        return Dinero(self.monto + otro.monto, self.moneda)


@dataclass(frozen=True)
class Cantidad:
    valor: int

    def __post_init__(self):
        if self.valor < 0:
            raise InvalidDomainData("La cantidad no puede ser negativa.")

    def sumar(self, otra: 'Cantidad') -> 'Cantidad':
        return Cantidad(self.valor + otra.valor)

    def restar(self, otra: 'Cantidad') -> 'Cantidad':
        if self.valor - otra.valor < 0:
            raise InvalidDomainData("La cantidad resultante no puede ser negativa.")
        return Cantidad(self.valor - otra.valor)


@dataclass(frozen=True)
class NumeroDeLote:
    codigo: str

    def __post_init__(self):
        if not self.codigo.strip():
            raise InvalidDomainData("El número de lote no puede estar vacío.")


class EstadoDelLote(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    RETIRADO = "RETIRADO"


#Reglas de Vendibilidad
class ReglaDeVendibilidad:
    def cumple(self, lote: 'Lote', hoy: date) -> bool:
        raise NotImplementedError
    
    def motivo(self) -> str:
        raise NotImplementedError


class LoteNoCaducado(ReglaDeVendibilidad):
    def cumple(self, lote: 'Lote', hoy: date) -> bool:
        return lote.caducidad >= hoy
    
    def motivo(self) -> str:
        return "El lote se encuentra caducado."


class LoteNoRetirado(ReglaDeVendibilidad):
    def cumple(self, lote: 'Lote', hoy: date) -> bool:
        return lote.estado == EstadoDelLote.DISPONIBLE
    
    def motivo(self) -> str:
        return "El lote ha sido retirado de la operación."


#Entidades y Agregados
@dataclass
class Lote:
    numero: NumeroDeLote
    caducidad: date
    cantidad: Cantidad
    estado: EstadoDelLote = EstadoDelLote.DISPONIBLE

    def es_vendible(self, hoy: date) -> tuple[bool, str]:
        reglas: List[ReglaDeVendibilidad] = [LoteNoCaducado(), LoteNoRetirado()]
        for regla in reglas:
            if not regla.cumple(self, hoy):
                return False, regla.motivo()
        return True, ""

    def descontar(self, cant: Cantidad) -> None:
        self.cantidad = self.cantidad.restar(cant)


@dataclass
class InventarioDeProducto:
    producto_id: str
    sucursal_id: str
    nivel_minimo: int
    lotes: List[Lote] = field(default_factory=list)

    @property
    def existencia_total(self) -> int:
        return sum(lote.cantidad.valor for lote in self.lotes)

    def esta_por_debajo_del_minimo(self) -> bool:
        return self.existencia_total < self.nivel_minimo

    def verificar_y_descontar(self, numero_lote: str, cantidad_a_vender: int, hoy: date) -> None:
        lote_encontrado = next((l for l in self.lotes if l.numero.codigo == numero_lote), None)
        if not lote_encontrado:
            raise InvalidDomainData("El lote especificado no existe en este inventario.")
        
        vendible, motivo = lote_encontrado.es_vendible(hoy)
        if not vendible:
            raise InvalidDomainData(f"Lote no vendible: {motivo}")
        
        if lote_encontrado.cantidad.valor < cantidad_a_vender:
            raise InvalidDomainData("Existencia insuficiente en el lote seleccionado.")
        
        lote_encontrado.descontar(Cantidad(cantidad_a_vender))

#Estados y Eventos de Dominio 
class EstadoVenta(str, Enum):
    EN_CAPTURA = "EN_CAPTURA"
    COMPLETADA = "COMPLETADA"
    RECHAZADA = "RECHAZADA"


class TipoValidacion(str, Enum):
    MEDICAMENTO = "MEDICAMENTO"
    CUIDADO_PERSONAL = "CUIDADO_PERSONAL"


class EstadoValidacion(str, Enum):
    NO_REQUERIDA = "NO_REQUERIDA"
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


@dataclass(frozen=True)
class EventoDeDominio:
    nombre: str
    venta_id: str
    ocurrido_en: date = field(default_factory=date.today)


@dataclass
class LineaDeVenta:
    producto_id: str
    numero_lote: NumeroDeLote
    cantidad: Cantidad
    precio_unitario: Dinero
    validacion: EstadoValidacion = EstadoValidacion.NO_REQUERIDA

    @property
    def subtotal(self) -> Dinero:
        return Dinero(self.precio_unitario.monto * Decimal(self.cantidad.valor), self.precio_unitario.moneda)

    def aprobar_validacion(self) -> None:
        if self.validacion == EstadoValidacion.PENDIENTE:
            self.validacion = EstadoValidacion.APROBADA

    def rechazar_validacion(self) -> None:
        if self.validacion == EstadoValidacion.PENDIENTE:
            self.validacion = EstadoValidacion.RECHAZADA


@dataclass
class Venta:
    id: str
    cajero_id: str
    sucursal_id: str
    estado: EstadoVenta = EstadoVenta.EN_CAPTURA
    lineas: List[LineaDeVenta] = field(default_factory=list)
    eventos: List[EventoDeDominio] = field(default_factory=list)

    @property
    def total(self) -> Dinero:
        monto_total = sum((linea.subtotal.monto for linea in self.lineas), Decimal("0"))
        return Dinero(monto_total)

    def agregar_linea(self, producto_id: str, numero_lote: NumeroDeLote, cantidad: Cantidad, precio_unitario: Dinero, requiere_validarcion: bool = False) -> None:
        if self.estado != EstadoVenta.EN_CAPTURA:
            raise InvalidOrderTransition("No se pueden agregar productos a una venta que no está en captura.")
        
        estado_val = EstadoValidacion.PENDIENTE if requiere_validarcion else EstadoValidacion.NO_REQUERIDA
        linea = LineaDeVenta(
            producto_id=producto_id,
            numero_lote=numero_lote,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            validacion=estado_val
        )
        self.lineas.append(linea)

    def puede_cobrarse(self) -> None:
        if not self.lineas:
            raise DomainException("La venta no contiene productos.")
        for linea in self.lineas:
            if linea.validacion == EstadoValidacion.PENDIENTE:
                raise DomainException("Existen productos con validaciones especiales pendientes por el responsable de farmacia (BR-04, BR-05).")
            if linea.validacion == EstadoValidacion.RECHAZADA:
                raise DomainException("La venta contiene productos con validación rechazada.")

    def completar(self) -> None:
        if self.estado == EstadoVenta.COMPLETADA:
            raise InvalidOrderTransition("Esta venta ya ha sido completada anteriormente.")
        if self.estado == EstadoVenta.RECHAZADA:
            raise InvalidOrderTransition("No se puede completar una venta que previamente fue rechazada.")
        
        self.puede_cobrarse()
        self.estado = EstadoVenta.COMPLETADA
        self.eventos.append(EventoDeDominio(nombre="VentaCompletada", venta_id=self.id))

    def rechazar(self, motivo: str) -> None:
        self.estado = EstadoVenta.RECHAZADA
        self.eventos.append(EventoDeDominio(nombre="VentaRechazada", venta_id=self.id))