from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional, Generic, TypeVar, Any

T = TypeVar("T")


# =====================================================================
# EXCEPCIONES DE DOMINIO
# =====================================================================
class DomainException(Exception):
    """Excepción base para violaciones de invariantes o reglas del dominio FarmaExpress."""
    pass


class InvalidDomainData(DomainException):
    """Datos inválidos o violación de reglas de negocio (BR-01 a BR-16)."""
    pass


class InvalidOrderTransition(DomainException):
    """Transición de estado inválida en una máquina de estados del dominio."""
    pass


class UnauthorizedRoleAction(DomainException):
    """Acción restringida por rol según el modelo de seguridad del negocio (RNF-01, RNF-07, BR-05, BR-14)."""
    pass


# =====================================================================
# ROLES Y ENUMERACIONES DEL LENGUAJE UBICUO (GLOSARIO Y BRD)
# =====================================================================
class RolUsuario(str, Enum):
    CAJERO = "cajero"
    RESPONSABLE_FARMACIA = "responsable_farmacia"
    COMPRAS = "compras"
    ALMACEN = "almacen"
    ADMINISTRACION = "administracion"


class TipoDeProducto(str, Enum):
    MEDICAMENTO = "MEDICAMENTO"
    CUIDADO_PERSONAL = "CUIDADO_PERSONAL"


# Alias para compatibilidad
TipoValidacion = TipoDeProducto


class EstadoDelLote(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    RETIRADO = "RETIRADO"


class EstadoVenta(str, Enum):
    EN_CAPTURA = "EN_CAPTURA"
    COMPLETADA = "COMPLETADA"
    RECHAZADA = "RECHAZADA"


class EstadoValidacion(str, Enum):
    NO_REQUERIDA = "NO_REQUERIDA"
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


class EstadoDeSustitucion(str, Enum):
    REGISTRADA = "REGISTRADA"
    APROBADA_POR_FARMACIA = "APROBADA_POR_FARMACIA"
    RECHAZADA_POR_FARMACIA = "RECHAZADA_POR_FARMACIA"
    ACEPTADA_POR_CLIENTE = "ACEPTADA_POR_CLIENTE"
    RECHAZADA_POR_CLIENTE = "RECHAZADA_POR_CLIENTE"


class EstadoDiferenciaInventario(str, Enum):
    PENDIENTE_REVISION = "PENDIENTE_REVISION"
    AJUSTE_APROBADO = "AJUSTE_APROBADO"
    AJUSTE_RECHAZADO = "AJUSTE_RECHAZADO"


class EstadoResurtido(str, Enum):
    PENDIENTE_ANALISIS = "PENDIENTE_ANALISIS"
    SOLICITADO_A_PROVEEDOR = "SOLICITADO_A_PROVEEDOR"
    DESCARTADO = "DESCARTADO"
    SURTIDO = "SURTIDO"


# =====================================================================
# NÚCLEO COMPARTIDO Y VALUE OBJECTS (MAPA DE DOMINIO + ADR-001/ADR-003)
# =====================================================================
@dataclass(frozen=True)
class ResultadoDeOperacion(Generic[T]):
    """Value Object que modela el resultado explícito de una operación de dominio (ADR-003)."""
    aceptada: bool
    valor: Optional[T] = None
    motivo: str = ""

    @classmethod
    def aceptar(cls, valor: Optional[T] = None, motivo: str = "") -> "ResultadoDeOperacion[T]":
        return cls(aceptada=True, valor=valor, motivo=motivo)

    @classmethod
    def rechazar(cls, motivo: str) -> "ResultadoDeOperacion[T]":
        return cls(aceptada=False, valor=None, motivo=motivo)


@dataclass(frozen=True)
class Dinero:
    monto: Decimal
    moneda: str = "MXN"

    def __post_init__(self):
        monto_dec = Decimal(str(self.monto)) if not isinstance(self.monto, Decimal) else self.monto
        object.__setattr__(self, "monto", monto_dec)
        if not self.monto.is_finite() or self.monto < 0:
            raise InvalidDomainData("El monto de dinero no puede ser negativo o no finito.")
        if not self.moneda or not self.moneda.strip():
            raise InvalidDomainData("La moneda es obligatoria.")

    def sumar(self, otro: "Dinero") -> "Dinero":
        if self.moneda != otro.moneda:
            raise InvalidDomainData("No se pueden sumar montos de diferentes monedas.")
        return Dinero(self.monto + otro.monto, self.moneda)

    def por(self, cantidad: "Cantidad") -> "Dinero":
        return Dinero(self.monto * Decimal(cantidad.valor), self.moneda)


@dataclass(frozen=True)
class Cantidad:
    valor: int

    def __post_init__(self):
        if not isinstance(self.valor, int) or isinstance(self.valor, bool) or self.valor < 0:
            raise InvalidDomainData("La cantidad no puede ser negativa.")

    def sumar(self, otra: "Cantidad") -> "Cantidad":
        return Cantidad(self.valor + otra.valor)

    def restar(self, otra: "Cantidad") -> "Cantidad":
        if self.valor - otra.valor < 0:
            raise InvalidDomainData("La cantidad resultante no puede ser negativa.")
        return Cantidad(self.valor - otra.valor)

    def alcanza_para(self, otra: "Cantidad") -> bool:
        return self.valor >= otra.valor


@dataclass(frozen=True)
class NumeroDeLote:
    codigo: str

    def __post_init__(self):
        if not self.codigo or not self.codigo.strip():
            raise InvalidDomainData("El número de lote no puede estar vacío.")


@dataclass(frozen=True)
class FechaDeCaducidad:
    """Value Object del Mapa de Dominio (D-04) para evaluar caducidad y proximidad."""
    fecha: date

    def __post_init__(self):
        if not isinstance(self.fecha, date):
            raise InvalidDomainData("La fecha de caducidad debe ser una fecha válida.")

    def fue_alcanzada(self, hoy: date) -> bool:
        """Indica si el lote ya caducó (BR-02)."""
        return self.fecha < hoy

    def esta_proxima(self, hoy: date, dias_alerta: int = 30) -> bool:
        """Indica si el lote no ha caducado pero se encuentra dentro del rango próximo a caducar (BR-11, BR-12)."""
        if self.fue_alcanzada(hoy):
            return False
        limite = hoy + timedelta(days=dias_alerta)
        return self.fecha <= limite


@dataclass(frozen=True)
class NivelMinimo:
    """Value Object del Mapa de Dominio (D-06, BR-09) para evaluar existencia baja por sucursal."""
    cantidad: Cantidad

    def __init__(self, valor_o_cantidad: int | Cantidad):
        if isinstance(valor_o_cantidad, Cantidad):
            object.__setattr__(self, "cantidad", valor_o_cantidad)
        else:
            object.__setattr__(self, "cantidad", Cantidad(int(valor_o_cantidad)))

    @property
    def valor(self) -> int:
        return self.cantidad.valor

    def esta_por_debajo(self, existencia: Cantidad | int) -> bool:
        val = existencia.valor if isinstance(existencia, Cantidad) else int(existencia)
        return val < self.cantidad.valor


@dataclass(frozen=True)
class RequisitoEspecial:
    """Value Object del Mapa de Dominio (D-08, BR-04) que indica si un medicamento exige validación."""
    descripcion: str = ""

    def aplica(self) -> bool:
        return bool(self.descripcion and self.descripcion.strip())


@dataclass(frozen=True)
class EstadoDeValidacion:
    """Value Object del Mapa de Dominio que conserva trazabilidad del responsable y fecha de validación (BR-05)."""
    tipo: EstadoValidacion
    responsable: Optional[str] = None
    fecha: Optional[date] = None
    motivo: str = ""

    @classmethod
    def no_requerida(cls) -> "EstadoDeValidacion":
        return cls(tipo=EstadoValidacion.NO_REQUERIDA)

    @classmethod
    def pendiente(cls) -> "EstadoDeValidacion":
        return cls(tipo=EstadoValidacion.PENDIENTE)

    def aprobar(self, responsable: str, fecha: date, motivo: str = "Requisitos validados") -> "EstadoDeValidacion":
        if not responsable or not responsable.strip():
            raise InvalidDomainData("Se requiere identificar al responsable de farmacia que aprueba la validación (BR-05).")
        nuevo_estado = MaquinaEstadoValidacion.transicionar(self.tipo, EstadoValidacion.APROBADA)
        return EstadoDeValidacion(tipo=nuevo_estado, responsable=responsable.strip(), fecha=fecha, motivo=motivo)

    def rechazar(self, responsable: str, fecha: date, motivo: str = "No cumple requisito especial") -> "EstadoDeValidacion":
        if not responsable or not responsable.strip():
            raise InvalidDomainData("Se requiere identificar al responsable de farmacia que rechaza la validación (BR-05).")
        nuevo_estado = MaquinaEstadoValidacion.transicionar(self.tipo, EstadoValidacion.RECHAZADA)
        return EstadoDeValidacion(tipo=nuevo_estado, responsable=responsable.strip(), fecha=fecha, motivo=motivo)


@dataclass(frozen=True)
class DecisionDeFarmacia:
    aprobada: bool
    responsable: str
    fecha: date
    observacion: str = ""

    def __post_init__(self):
        if not self.responsable or not self.responsable.strip():
            raise InvalidDomainData("El responsable de farmacia es obligatorio para validar una sustitución (BR-08).")


@dataclass(frozen=True)
class DecisionDelCliente:
    acepta: bool
    fecha: date


@dataclass(frozen=True)
class PoliticaFarmaExpress:
    """Políticas configurables del negocio (BR-12: periodo de proximidad a caducidad)."""
    dias_proximidad_caducidad: int = 30

    def __post_init__(self):
        if self.dias_proximidad_caducidad < 1 or self.dias_proximidad_caducidad > 365:
            raise InvalidDomainData("El periodo de proximidad a caducidad debe estar entre 1 y 365 días (BR-12).")


# =====================================================================
# STATE MACHINES EXPLÍCITAS (REQUISITO DE IMPLEMENTACIÓN REQ_PIA)
# =====================================================================
class MaquinaEstadoVenta:
    """State Machine que gobierna el ciclo de vida del Aggregate Venta."""
    TRANSICIONES = {
        EstadoVenta.EN_CAPTURA: {EstadoVenta.COMPLETADA, EstadoVenta.RECHAZADA},
        EstadoVenta.COMPLETADA: set(),
        EstadoVenta.RECHAZADA: set(),
    }

    @classmethod
    def transicionar(cls, actual: EstadoVenta, destino: EstadoVenta) -> EstadoVenta:
        if destino not in cls.TRANSICIONES.get(actual, set()):
            if actual == EstadoVenta.COMPLETADA:
                raise InvalidOrderTransition("Esta venta ya ha sido completada anteriormente.")
            if actual == EstadoVenta.RECHAZADA:
                raise InvalidOrderTransition("No se puede modificar ni completar una venta que previamente fue rechazada.")
            raise InvalidOrderTransition(f"Transición de estado de venta inválida: {actual.value} -> {destino.value}")
        return destino


class MaquinaEstadoLote:
    """State Machine para el control de estado de lotes (DISPONIBLE -> RETIRADO, BR-03 / US-06)."""
    TRANSICIONES = {
        EstadoDelLote.DISPONIBLE: {EstadoDelLote.RETIRADO},
        EstadoDelLote.RETIRADO: set(),  # Un lote retirado queda bloqueado permanentemente por seguridad sanitaria
    }

    @classmethod
    def transicionar(cls, actual: EstadoDelLote, destino: EstadoDelLote) -> EstadoDelLote:
        if destino not in cls.TRANSICIONES.get(actual, set()):
            raise InvalidOrderTransition(f"El lote en estado {actual.value} no puede pasar a {destino.value} (BR-03).")
        return destino


class MaquinaEstadoValidacion:
    """State Machine para la validación de medicamentos con requisitos especiales (BR-04, BR-05)."""
    TRANSICIONES = {
        EstadoValidacion.NO_REQUERIDA: set(),
        EstadoValidacion.PENDIENTE: {EstadoValidacion.APROBADA, EstadoValidacion.RECHAZADA},
        EstadoValidacion.APROBADA: set(),
        EstadoValidacion.RECHAZADA: set(),
    }

    @classmethod
    def transicionar(cls, actual: EstadoValidacion, destino: EstadoValidacion) -> EstadoValidacion:
        if destino not in cls.TRANSICIONES.get(actual, set()):
            raise InvalidOrderTransition(f"La validación en estado {actual.value} no puede cambiar a {destino.value}.")
        return destino


class MaquinaEstadoSustitucion:
    """State Machine para el flujo de SolicitudDeSustitucion (CU-03, BR-08, US-07, US-08)."""
    TRANSICIONES = {
        EstadoDeSustitucion.REGISTRADA: {
            EstadoDeSustitucion.APROBADA_POR_FARMACIA,
            EstadoDeSustitucion.RECHAZADA_POR_FARMACIA,
        },
        EstadoDeSustitucion.APROBADA_POR_FARMACIA: {
            EstadoDeSustitucion.ACEPTADA_POR_CLIENTE,
            EstadoDeSustitucion.RECHAZADA_POR_CLIENTE,
        },
        EstadoDeSustitucion.RECHAZADA_POR_FARMACIA: set(),
        EstadoDeSustitucion.ACEPTADA_POR_CLIENTE: set(),
        EstadoDeSustitucion.RECHAZADA_POR_CLIENTE: set(),
    }

    @classmethod
    def transicionar(cls, actual: EstadoDeSustitucion, destino: EstadoDeSustitucion) -> EstadoDeSustitucion:
        if destino not in cls.TRANSICIONES.get(actual, set()):
            raise InvalidOrderTransition(f"Transición de sustitución inválida: {actual.value} -> {destino.value}")
        return destino


class MaquinaEstadoDiferencia:
    """State Machine para la revisión y autorización de diferencias de inventario (BR-13, RF-14, RF-15)."""
    TRANSICIONES = {
        EstadoDiferenciaInventario.PENDIENTE_REVISION: {
            EstadoDiferenciaInventario.AJUSTE_APROBADO,
            EstadoDiferenciaInventario.AJUSTE_RECHAZADO,
        },
        EstadoDiferenciaInventario.AJUSTE_APROBADO: set(),
        EstadoDiferenciaInventario.AJUSTE_RECHAZADO: set(),
    }

    @classmethod
    def transicionar(cls, actual: EstadoDiferenciaInventario, destino: EstadoDiferenciaInventario) -> EstadoDiferenciaInventario:
        if destino not in cls.TRANSICIONES.get(actual, set()):
            raise InvalidOrderTransition(f"La diferencia de inventario ya fue resuelta ({actual.value}).")
        return destino


class MaquinaEstadoResurtido:
    """State Machine para el análisis manual de resurtido por Compras (BR-09, BR-10, US-11, US-12)."""
    TRANSICIONES = {
        EstadoResurtido.PENDIENTE_ANALISIS: {
            EstadoResurtido.SOLICITADO_A_PROVEEDOR,
            EstadoResurtido.DESCARTADO,
        },
        EstadoResurtido.SOLICITADO_A_PROVEEDOR: {EstadoResurtido.SURTIDO},
        EstadoResurtido.DESCARTADO: set(),
        EstadoResurtido.SURTIDO: set(),
    }

    @classmethod
    def transicionar(cls, actual: EstadoResurtido, destino: EstadoResurtido) -> EstadoResurtido:
        if destino not in cls.TRANSICIONES.get(actual, set()):
            raise InvalidOrderTransition(f"Transición de resurtido inválida: {actual.value} -> {destino.value}")
        return destino


# =====================================================================
# PATRÓN SPECIFICATION Y REGLAS DE VENDIBILIDAD (ADR-006 + REQ_PIA)
# =====================================================================
class Specification:
    """Patrón Specification componible con operadores lógicos (&, |, ~)."""
    def is_satisfied_by(self, candidate: Any, context: Any = None) -> bool:
        raise NotImplementedError

    def __and__(self, other: "Specification") -> "AndSpecification":
        return AndSpecification(self, other)

    def __or__(self, other: "Specification") -> "OrSpecification":
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification":
        return NotSpecification(self)


class AndSpecification(Specification):
    def __init__(self, left: Specification, right: Specification):
        self.left = left
        self.right = right

    def is_satisfied_by(self, candidate: Any, context: Any = None) -> bool:
        return self.left.is_satisfied_by(candidate, context) and self.right.is_satisfied_by(candidate, context)


class OrSpecification(Specification):
    def __init__(self, left: Specification, right: Specification):
        self.left = left
        self.right = right

    def is_satisfied_by(self, candidate: Any, context: Any = None) -> bool:
        return self.left.is_satisfied_by(candidate, context) or self.right.is_satisfied_by(candidate, context)


class NotSpecification(Specification):
    def __init__(self, spec: Specification):
        self.spec = spec

    def is_satisfied_by(self, candidate: Any, context: Any = None) -> bool:
        return not self.spec.is_satisfied_by(candidate, context)


class ReglaDeVendibilidad(Specification):
    """Estrategia / Specification intercambiable de vendibilidad de un lote (ADR-006)."""
    def cumple(self, lote: "Lote", hoy: date) -> bool:
        raise NotImplementedError

    def motivo(self) -> str:
        raise NotImplementedError

    def is_satisfied_by(self, candidate: "Lote", context: Optional[date] = None) -> bool:
        hoy = context or date.today()
        return self.cumple(candidate, hoy)


class LoteNoCaducado(ReglaDeVendibilidad):
    """BR-02: No vender productos caducados."""
    def cumple(self, lote: "Lote", hoy: date) -> bool:
        return lote.caducidad >= hoy

    def motivo(self) -> str:
        return "El lote se encuentra caducado (BR-02)."


class LoteNoRetirado(ReglaDeVendibilidad):
    """BR-03: Bloquear lotes retirados de la operación."""
    def cumple(self, lote: "Lote", hoy: date) -> bool:
        return lote.estado == EstadoDelLote.DISPONIBLE

    def motivo(self) -> str:
        return "El lote ha sido retirado de la operación (BR-03)."


class LoteConExistenciaSuficiente(ReglaDeVendibilidad):
    """BR-01: No vender productos sin existencia suficiente."""
    def __init__(self, cantidad_requerida: int = 1):
        self.cantidad_requerida = cantidad_requerida

    def cumple(self, lote: "Lote", hoy: date) -> bool:
        return lote.cantidad.valor >= self.cantidad_requerida

    def motivo(self) -> str:
        return "Existencia insuficiente en el lote seleccionado (BR-01)."


class LoteProximoACaducarSpec(Specification):
    """BR-11 y BR-12: Identifica si un lote disponible está dentro del periodo de proximidad a caducidad."""
    def __init__(self, dias_alerta: int = 30):
        self.dias_alerta = dias_alerta

    def is_satisfied_by(self, lote: "Lote", hoy: Optional[date] = None) -> bool:
        fecha_ref = hoy or date.today()
        if lote.estado != EstadoDelLote.DISPONIBLE:
            return False
        return FechaDeCaducidad(lote.caducidad).esta_proxima(fecha_ref, self.dias_alerta)


class InventarioBajoMinimoSpec(Specification):
    """BR-09: Identifica cuando la existencia disponible de un producto cae por debajo del nivel mínimo."""
    def is_satisfied_by(self, inventario: "InventarioDeProducto", hoy: Optional[date] = None) -> bool:
        return inventario.esta_por_debajo_del_minimo(hoy)


class VentaListaParaCobroSpec(Specification):
    """BR-04 y BR-05: Verifica que una venta tenga líneas y todas las validaciones especiales aprobadas."""
    def is_satisfied_by(self, venta: "Venta", context: Any = None) -> bool:
        if venta.estado != EstadoVenta.EN_CAPTURA or not venta.lineas:
            return False
        return all(
            linea.validacion in (EstadoValidacion.NO_REQUERIDA, EstadoValidacion.APROBADA)
            for linea in venta.lineas
        )


# =====================================================================
# EVENTOS DE DOMINIO (MAPA DE DOMINIO + ADR-004)
# =====================================================================
@dataclass(frozen=True)
class EventoDeDominio:
    nombre: str
    venta_id: str = ""
    ocurrido_en: date = field(default_factory=date.today)
    detalles: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VentaCompletada(EventoDeDominio):
    sucursal_id: str = ""
    total_monto: Decimal = Decimal("0.00")

    def __init__(self, venta_id: str, sucursal_id: str = "", total: Optional[Dinero] = None, ocurrido_en: Optional[date] = None):
        fecha = ocurrido_en or date.today()
        monto = total.monto if total else Decimal("0.00")
        super().__init__(
            nombre="VentaCompletada",
            venta_id=venta_id,
            ocurrido_en=fecha,
            detalles={"venta_id": venta_id, "sucursal_id": sucursal_id, "total": str(monto)},
        )
        object.__setattr__(self, "sucursal_id", sucursal_id)
        object.__setattr__(self, "total_monto", monto)


@dataclass(frozen=True)
class VentaRechazada(EventoDeDominio):
    motivo: str = ""

    def __init__(self, venta_id: str, motivo: str = "", ocurrido_en: Optional[date] = None):
        fecha = ocurrido_en or date.today()
        super().__init__(
            nombre="VentaRechazada",
            venta_id=venta_id,
            ocurrido_en=fecha,
            detalles={"venta_id": venta_id, "motivo": motivo},
        )
        object.__setattr__(self, "motivo", motivo)


@dataclass(frozen=True)
class ExistenciaBajaDetectada(EventoDeDominio):
    producto_id: str = ""
    sucursal_id: str = ""
    existencia_actual: int = 0
    nivel_minimo: int = 0

    def __init__(
        self,
        producto_id: str,
        sucursal_id: str,
        existencia_actual: int,
        nivel_minimo: int,
        ocurrido_en: Optional[date] = None,
    ):
        fecha = ocurrido_en or date.today()
        super().__init__(
            nombre="ExistenciaBajaDetectada",
            venta_id="",
            ocurrido_en=fecha,
            detalles={
                "producto_id": producto_id,
                "sucursal_id": sucursal_id,
                "existencia_actual": existencia_actual,
                "nivel_minimo": nivel_minimo,
            },
        )
        object.__setattr__(self, "producto_id", producto_id)
        object.__setattr__(self, "sucursal_id", sucursal_id)
        object.__setattr__(self, "existencia_actual", existencia_actual)
        object.__setattr__(self, "nivel_minimo", nivel_minimo)


@dataclass(frozen=True)
class MercanciaRecibida(EventoDeDominio):
    recepcion_id: str = ""
    sucursal_id: str = ""

    def __init__(self, recepcion_id: str, sucursal_id: str, ocurrido_en: Optional[date] = None):
        fecha = ocurrido_en or date.today()
        super().__init__(
            nombre="MercanciaRecibida",
            venta_id="",
            ocurrido_en=fecha,
            detalles={"recepcion_id": recepcion_id, "sucursal_id": sucursal_id},
        )
        object.__setattr__(self, "recepcion_id", recepcion_id)
        object.__setattr__(self, "sucursal_id", sucursal_id)


@dataclass(frozen=True)
class SustitucionResuelta(EventoDeDominio):
    solicitud_id: str = ""
    resultado: str = ""

    def __init__(self, solicitud_id: str, venta_id: str, resultado: str, ocurrido_en: Optional[date] = None):
        fecha = ocurrido_en or date.today()
        super().__init__(
            nombre="SustitucionResuelta",
            venta_id=venta_id,
            ocurrido_en=fecha,
            detalles={"solicitud_id": solicitud_id, "venta_id": venta_id, "resultado": resultado},
        )
        object.__setattr__(self, "solicitud_id", solicitud_id)
        object.__setattr__(self, "resultado", resultado)


# =====================================================================
# AGGREGATE 1: PRODUCTO (CATÁLOGO - ADR-002 Y MAPA DE DOMINIO)
# =====================================================================
@dataclass
class Producto:
    """Aggregate Root del catálogo de FarmaExpress (D-01, D-08, BR-04)."""
    id: str
    nombre: str
    tipo: TipoDeProducto
    precio: Dinero
    requisito: RequisitoEspecial = field(default_factory=RequisitoEspecial)
    sustitutos_ids: List[str] = field(default_factory=list)
    categoria: str = "General"

    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise InvalidDomainData("El identificador del producto es obligatorio.")
        if not self.nombre or not self.nombre.strip():
            raise InvalidDomainData("El nombre del producto es obligatorio.")

    def requiere_validacion_especial(self) -> bool:
        """BR-04: Indica si el medicamento está sujeto a requisitos especiales antes de su venta."""
        return self.tipo == TipoDeProducto.MEDICAMENTO and self.requisito.aplica()


# =====================================================================
# AGGREGATE 2: INVENTARIO DE PRODUCTO Y ENTIDAD LOTE (ADR-002, BR-01..03, BR-06, BR-09)
# =====================================================================
@dataclass
class Lote:
    numero: NumeroDeLote
    caducidad: date
    cantidad: Cantidad
    estado: EstadoDelLote = EstadoDelLote.DISPONIBLE
    motivo_retiro: str = ""
    retirado_por: Optional[str] = None
    fecha_retiro: Optional[date] = None

    @property
    def fecha_caducidad_vo(self) -> FechaDeCaducidad:
        return FechaDeCaducidad(self.caducidad)

    def esta_caducado(self, hoy: date) -> bool:
        return self.fecha_caducidad_vo.fue_alcanzada(hoy)

    def esta_proximo_a_caducar(self, hoy: date, dias_alerta: int = 30) -> bool:
        return LoteProximoACaducarSpec(dias_alerta).is_satisfied_by(self, hoy)

    def es_vendible(self, hoy: date, reglas_extra: Optional[List[ReglaDeVendibilidad]] = None) -> tuple[bool, str]:
        """Evalúa las estrategias de vendibilidad intercambiables (ADR-006)."""
        reglas: List[ReglaDeVendibilidad] = [LoteNoRetirado(), LoteNoCaducado()]
        if reglas_extra:
            reglas.extend(reglas_extra)
        for regla in reglas:
            if not regla.cumple(self, hoy):
                return False, regla.motivo()
        return True, ""

    def descontar(self, cant: Cantidad) -> None:
        if cant.valor <= 0:
            raise InvalidDomainData("La cantidad a descontar debe ser mayor a cero.")
        self.cantidad = self.cantidad.restar(cant)

    def agregar(self, cant: Cantidad) -> None:
        if cant.valor <= 0:
            raise InvalidDomainData("La cantidad a ingresar debe ser mayor a cero.")
        self.cantidad = self.cantidad.sumar(cant)

    def retirar(self, responsable: str, motivo: str, hoy: Optional[date] = None) -> None:
        """US-06 / BR-03: Bloquea el lote como RETIRADO para impedir su comercialización."""
        if not responsable or not responsable.strip():
            raise InvalidDomainData("Debe indicarse el responsable de farmacia que retira el lote.")
        if not motivo or not motivo.strip():
            raise InvalidDomainData("Debe registrarse el motivo del retiro del lote.")
        self.estado = MaquinaEstadoLote.transicionar(self.estado, EstadoDelLote.RETIRADO)
        self.retirado_por = responsable.strip()
        self.motivo_retiro = motivo.strip()
        self.fecha_retiro = hoy or date.today()


@dataclass
class InventarioDeProducto:
    """
    Aggregate Root que controla las existencias de un producto en una sucursal específica (ADR-002, ADR-007).
    Evalúa el nivel mínimo sobre la suma de lotes en esa sucursal (BR-09).
    """
    producto_id: str
    sucursal_id: str
    nivel_minimo: int
    lotes: List[Lote] = field(default_factory=list)
    eventos: List[EventoDeDominio] = field(default_factory=list)

    @property
    def nivel_minimo_vo(self) -> NivelMinimo:
        return NivelMinimo(self.nivel_minimo)

    @property
    def existencia_total(self) -> int:
        return sum(lote.cantidad.valor for lote in self.lotes)

    def existencia_vendible(self, hoy: Optional[date] = None) -> int:
        """Suma únicamente la existencia de lotes disponibles y no caducados (Glosario: Producto disponible para venta)."""
        fecha_ref = hoy or date.today()
        return sum(
            lote.cantidad.valor
            for lote in self.lotes
            if lote.es_vendible(fecha_ref)[0]
        )

    def esta_por_debajo_del_minimo(self, hoy: Optional[date] = None) -> bool:
        """BR-09: Indica si la existencia del producto en la sucursal cayó por debajo del nivel mínimo."""
        if hoy is not None:
            return self.existencia_vendible(hoy) < self.nivel_minimo_vo.valor
        return self.existencia_total < self.nivel_minimo_vo.valor

    def obtener_lote(self, numero_lote: str) -> Optional[Lote]:
        return next((l for l in self.lotes if l.numero.codigo == numero_lote), None)

    def verificar_venta(self, numero_lote: str, cantidad_a_vender: int, hoy: date) -> ResultadoDeOperacion[Lote]:
        """Verifica sin descontar si un lote puede surtir la cantidad solicitada (CU-01, CU-04)."""
        if cantidad_a_vender <= 0:
            return ResultadoDeOperacion.rechazar("La cantidad a vender debe ser un entero positivo mayor a cero.")
        lote_encontrado = self.obtener_lote(numero_lote)
        if not lote_encontrado:
            return ResultadoDeOperacion.rechazar("El lote especificado no existe en este inventario.")
        vendible, motivo = lote_encontrado.es_vendible(hoy)
        if not vendible:
            return ResultadoDeOperacion.rechazar(f"Lote no vendible: {motivo}")
        if not LoteConExistenciaSuficiente(cantidad_a_vender).cumple(lote_encontrado, hoy):
            return ResultadoDeOperacion.rechazar(
                f"Existencia insuficiente en el lote {numero_lote} (disponible: {lote_encontrado.cantidad.valor}, solicitado: {cantidad_a_vender}) (BR-01)."
            )
        return ResultadoDeOperacion.aceptar(lote_encontrado)

    def asignar_lote(self, cantidad_requerida: int, hoy: date) -> ResultadoDeOperacion[NumeroDeLote]:
        """
        Selecciona automáticamente el lote vendible con caducidad más próxima (FEFO) que tenga existencia suficiente
        (Mapa de Dominio y Secuencia 2 paso 27).
        """
        if cantidad_requerida <= 0:
            return ResultadoDeOperacion.rechazar("La cantidad requerida debe ser mayor a cero.")
        candidatos = [
            l for l in self.lotes
            if l.es_vendible(hoy)[0] and l.cantidad.valor >= cantidad_requerida
        ]
        if not candidatos:
            return ResultadoDeOperacion.rechazar(
                f"El producto {self.producto_id} no cuenta con un lote vendible con existencia suficiente ({cantidad_requerida}) en la sucursal {self.sucursal_id} (BR-01)."
            )
        candidatos.sort(key=lambda l: l.caducidad)
        return ResultadoDeOperacion.aceptar(candidatos[0].numero)

    def verificar_y_descontar(self, numero_lote: str, cantidad_a_vender: int, hoy: date) -> None:
        """
        Verifica disponibilidad/vendibilidad, descuenta la existencia (BR-06, BR-07, US-17)
        y emite el evento ExistenciaBajaDetectada si cae bajo el nivel mínimo (BR-09, US-11).
        """
        verificacion = self.verificar_venta(numero_lote, cantidad_a_vender, hoy)
        if not verificacion.aceptada or verificacion.valor is None:
            raise InvalidDomainData(verificacion.motivo)

        verificacion.valor.descontar(Cantidad(cantidad_a_vender))

        if self.esta_por_debajo_del_minimo(hoy):
            self.eventos.append(
                ExistenciaBajaDetectada(
                    producto_id=self.producto_id,
                    sucursal_id=self.sucursal_id,
                    existencia_actual=self.existencia_vendible(hoy),
                    nivel_minimo=self.nivel_minimo_vo.valor,
                    ocurrido_en=hoy,
                )
            )

    def registrar_entrada(self, numero_lote: NumeroDeLote, caducidad: date, cantidad: Cantidad, hoy: date) -> None:
        """BR-06 y BR-15 (US-14): Registra el ingreso de mercancía en almacén validando lote y caducidad."""
        if cantidad.valor <= 0:
            raise InvalidDomainData("La cantidad recibida en almacén debe ser mayor a cero.")
        if FechaDeCaducidad(caducidad).fue_alcanzada(hoy):
            raise InvalidDomainData(f"No se puede recibir en almacén el lote {numero_lote.codigo} porque ya está caducado ({caducidad}) (BR-02, BR-15).")

        existente = self.obtener_lote(numero_lote.codigo)
        if existente:
            if existente.estado == EstadoDelLote.RETIRADO:
                raise InvalidDomainData(f"No se puede agregar mercancía al lote {numero_lote.codigo} porque fue retirado de la operación (BR-03).")
            if existente.caducidad != caducidad:
                raise InvalidDomainData(
                    f"El lote {numero_lote.codigo} ya existe con fecha de caducidad {existente.caducidad}; no coincide con {caducidad} (RNF-02)."
                )
            existente.agregar(cantidad)
        else:
            self.lotes.append(
                Lote(
                    numero=numero_lote,
                    caducidad=caducidad,
                    cantidad=cantidad,
                    estado=EstadoDelLote.DISPONIBLE,
                )
            )

    def retirar_lote(self, numero_lote: str, responsable: str, motivo: str, hoy: Optional[date] = None) -> Lote:
        """US-06 / BR-03: Marca un lote como retirado dentro del inventario."""
        lote = self.obtener_lote(numero_lote)
        if not lote:
            raise InvalidDomainData(f"El lote {numero_lote} no existe en el inventario del producto {self.producto_id}.")
        lote.retirar(responsable=responsable, motivo=motivo, hoy=hoy)
        self.eventos.append(
            EventoDeDominio(
                nombre="LoteRetirado",
                ocurrido_en=hoy or date.today(),
                detalles={
                    "producto_id": self.producto_id,
                    "sucursal_id": self.sucursal_id,
                    "lote": numero_lote,
                    "responsable": responsable,
                    "motivo": motivo,
                },
            )
        )
        return lote

    def aplicar_ajuste_autorizado(self, numero_lote: str, nueva_cantidad_fisica: int, responsable: str, motivo: str, hoy: Optional[date] = None) -> None:
        """BR-13, RF-15, RNF-08: Ajusta la existencia de un lote únicamente tras una revisión autorizada."""
        if not responsable or not responsable.strip():
            raise InvalidDomainData("Todo ajuste de inventario requiere un responsable autorizado (RF-15, RNF-08).")
        lote = self.obtener_lote(numero_lote)
        if not lote:
            raise InvalidDomainData(f"El lote {numero_lote} no existe en el inventario.")
        anterior = lote.cantidad.valor
        lote.cantidad = Cantidad(nueva_cantidad_fisica)
        self.eventos.append(
            EventoDeDominio(
                nombre="AjusteDeInventarioAplicado",
                ocurrido_en=hoy or date.today(),
                detalles={
                    "producto_id": self.producto_id,
                    "sucursal_id": self.sucursal_id,
                    "lote": numero_lote,
                    "cantidad_anterior": anterior,
                    "cantidad_ajustada": nueva_cantidad_fisica,
                    "responsable": responsable,
                    "motivo": motivo,
                },
            )
        )


# =====================================================================
# AGGREGATE 3: VENTA Y ENTIDAD LINEA DE VENTA (ADR-002, BR-01..05, CU-01, CU-02, CU-04)
# =====================================================================
@dataclass
class LineaDeVenta:
    producto_id: str
    numero_lote: NumeroDeLote
    cantidad: Cantidad
    precio_unitario: Dinero
    validacion: EstadoValidacion = EstadoValidacion.NO_REQUERIDA
    id: str = ""
    nombre_producto: str = ""
    requisito_descripcion: str = ""
    responsable_validacion: Optional[str] = None
    fecha_validacion: Optional[date] = None
    motivo_validacion: str = ""

    def __post_init__(self):
        if self.cantidad.valor <= 0:
            raise InvalidDomainData("La cantidad de productos en una línea de venta debe ser mayor a cero.")
        if not self.id:
            self.id = f"LIN-{self.producto_id}-{self.numero_lote.codigo}"

    @property
    def subtotal(self) -> Dinero:
        return Dinero(self.precio_unitario.monto * Decimal(self.cantidad.valor), self.precio_unitario.moneda)

    def aprobar_validacion(self, responsable: str = "RESP-FARMACIA", hoy: Optional[date] = None, motivo: str = "Requisito especial verificado") -> None:
        if self.validacion == EstadoValidacion.PENDIENTE:
            vo = EstadoDeValidacion(self.validacion).aprobar(responsable, hoy or date.today(), motivo)
            self.validacion = vo.tipo
            self.responsable_validacion = vo.responsable
            self.fecha_validacion = vo.fecha
            self.motivo_validacion = vo.motivo
        else:
            raise InvalidOrderTransition(f"La línea {self.id} no tiene una validación pendiente (estado actual: {self.validacion.value}).")

    def rechazar_validacion(self, responsable: str = "RESP-FARMACIA", hoy: Optional[date] = None, motivo: str = "No cumple requisito especial") -> None:
        if self.validacion == EstadoValidacion.PENDIENTE:
            vo = EstadoDeValidacion(self.validacion).rechazar(responsable, hoy or date.today(), motivo)
            self.validacion = vo.tipo
            self.responsable_validacion = vo.responsable
            self.fecha_validacion = vo.fecha
            self.motivo_validacion = vo.motivo
        else:
            raise InvalidOrderTransition(f"La línea {self.id} no tiene una validación pendiente (estado actual: {self.validacion.value}).")


@dataclass
class Venta:
    """Aggregate Root que modela la operación de venta en una sucursal (ADR-001, ADR-002)."""
    id: str
    cajero_id: str
    sucursal_id: str
    estado: EstadoVenta = EstadoVenta.EN_CAPTURA
    motivo_de_rechazo: str = ""
    lineas: List[LineaDeVenta] = field(default_factory=list)
    eventos: List[EventoDeDominio] = field(default_factory=list)

    def esta_en_captura(self) -> bool:
        return self.estado == EstadoVenta.EN_CAPTURA

    @property
    def total(self) -> Dinero:
        monto_total = sum((linea.subtotal.monto for linea in self.lineas), Decimal("0.00"))
        return Dinero(monto_total)

    @property
    def requiere_validacion_responsable(self) -> bool:
        return any(l.validacion == EstadoValidacion.PENDIENTE for l in self.lineas)

    def agregar_linea(
        self,
        producto_id: str,
        numero_lote: NumeroDeLote,
        cantidad: Cantidad,
        precio_unitario: Dinero,
        requiere_validarcion: bool = False,
        nombre_producto: str = "",
        requisito_descripcion: str = "",
    ) -> LineaDeVenta:
        if not self.esta_en_captura():
            raise InvalidOrderTransition("No se pueden agregar productos a una venta que no está en captura.")
        if cantidad.valor <= 0:
            raise InvalidDomainData("La cantidad a agregar en la venta debe ser un entero positivo mayor a cero.")

        estado_val = EstadoValidacion.PENDIENTE if requiere_validarcion else EstadoValidacion.NO_REQUERIDA
        linea_id = f"L{len(self.lineas) + 1}-{producto_id}"
        linea = LineaDeVenta(
            id=linea_id,
            producto_id=producto_id,
            numero_lote=numero_lote,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            validacion=estado_val,
            nombre_producto=nombre_producto or producto_id,
            requisito_descripcion=requisito_descripcion or ("Requisito médico especial (BR-04)" if requiere_validarcion else ""),
        )
        self.lineas.append(linea)
        return linea

    def agregar_producto(self, producto: Producto, numero_lote: NumeroDeLote, cantidad: Cantidad) -> LineaDeVenta:
        """Método del Mapa de Dominio que recibe el Aggregate Producto y evalúa automáticamente BR-04."""
        return self.agregar_linea(
            producto_id=producto.id,
            numero_lote=numero_lote,
            cantidad=cantidad,
            precio_unitario=producto.precio,
            requiere_validarcion=producto.requiere_validacion_especial(),
            nombre_producto=producto.nombre,
            requisito_descripcion=producto.requisito.descripcion,
        )

    def resolver_validacion(
        self,
        identificador_linea_o_producto: str,
        aprueba: bool,
        responsable_id: str,
        hoy: Optional[date] = None,
        motivo: str = "",
        rol_usuario: str = RolUsuario.RESPONSABLE_FARMACIA.value,
    ) -> LineaDeVenta:
        """
        CU-02 / US-03 / BR-04 / BR-05: El Responsable de Farmacia aprueba o rechaza la validación de un medicamento.
        Si el cajero intenta resolverla, se rechaza por BR-05 y RNF-01.
        """
        if rol_usuario != RolUsuario.RESPONSABLE_FARMACIA.value:
            raise UnauthorizedRoleAction(
                "El cajero u otro rol no está autorizado para validar requisitos especiales; debe intervenir el Responsable de Farmacia (BR-05, RNF-01)."
            )
        if not self.esta_en_captura():
            raise InvalidOrderTransition("No se pueden resolver validaciones de una venta que ya fue cerrada.")

        linea = next(
            (
                l for l in self.lineas
                if l.id == identificador_linea_o_producto or l.producto_id == identificador_linea_o_producto
            ),
            None,
        )
        if not linea:
            raise InvalidDomainData(f"No se encontró la línea o producto '{identificador_linea_o_producto}' en la venta {self.id}.")

        fecha = hoy or date.today()
        if aprueba:
            linea.aprobar_validacion(responsable=responsable_id, hoy=fecha, motivo=motivo or "Receta y requisito especial verificados")
            self.eventos.append(
                EventoDeDominio(
                    nombre="ValidacionEspecialAprobada",
                    venta_id=self.id,
                    ocurrido_en=fecha,
                    detalles={"linea_id": linea.id, "producto_id": linea.producto_id, "responsable": responsable_id},
                )
            )
        else:
            motivo_rechazo = motivo or "El cliente no presentó la receta o requisito especial obligatorio (BR-04)"
            linea.rechazar_validacion(responsable=responsable_id, hoy=fecha, motivo=motivo_rechazo)
            self.rechazar(f"Validación especial rechazada por farmacia: {motivo_rechazo}", hoy=fecha)

        return linea

    def puede_cobrarse(self) -> None:
        if not self.lineas:
            raise InvalidDomainData("La venta no contiene productos.")
        for linea in self.lineas:
            if linea.validacion == EstadoValidacion.PENDIENTE:
                raise InvalidDomainData(
                    f"Existen medicamentos ({linea.producto_id}) con validaciones especiales pendientes por el Responsable de Farmacia (BR-04, BR-05)."
                )
            if linea.validacion == EstadoValidacion.RECHAZADA:
                raise InvalidDomainData(
                    f"La venta contiene medicamentos ({linea.producto_id}) con validación especial rechazada."
                )

    def completar(self, hoy: Optional[date] = None) -> None:
        nuevo_estado = MaquinaEstadoVenta.transicionar(self.estado, EstadoVenta.COMPLETADA)
        self.puede_cobrarse()
        self.estado = nuevo_estado
        self.eventos.append(
            VentaCompletada(
                venta_id=self.id,
                sucursal_id=self.sucursal_id,
                total=self.total,
                ocurrido_en=hoy or date.today(),
            )
        )

    def rechazar(self, motivo: str, hoy: Optional[date] = None) -> None:
        nuevo_estado = MaquinaEstadoVenta.transicionar(self.estado, EstadoVenta.RECHAZADA)
        self.estado = nuevo_estado
        self.motivo_de_rechazo = motivo
        self.eventos.append(
            VentaRechazada(
                venta_id=self.id,
                motivo=motivo,
                ocurrido_en=hoy or date.today(),
            )
        )


# =====================================================================
# AGGREGATE 4: SOLICITUD DE SUSTITUCIÓN (MAPA DE DOMINIO, SECUENCIA 2, CU-03, BR-08, US-07, US-08)
# =====================================================================
@dataclass
class SolicitudDeSustitucion:
    """
    Aggregate Root que gestiona la solicitud de una alternativa cuando un producto no tiene existencia (CU-03).
    """
    id: str
    venta_id: str
    producto_original: str
    cantidad: Cantidad
    alternativa: Optional[str] = None
    estado: EstadoDeSustitucion = EstadoDeSustitucion.REGISTRADA
    decision_farmacia: Optional[DecisionDeFarmacia] = None
    decision_cliente: Optional[DecisionDelCliente] = None
    motivo: str = "Producto solicitado sin existencia disponible"
    eventos: List[EventoDeDominio] = field(default_factory=list)

    @classmethod
    def registrar(
        cls,
        id: str,
        venta_id: str,
        producto_original: str,
        cantidad: Cantidad,
        motivo: str = "Producto original sin existencia disponible",
    ) -> "SolicitudDeSustitucion":
        if cantidad.valor <= 0:
            raise InvalidDomainData("La cantidad para sustitución debe ser mayor a cero.")
        return cls(
            id=id,
            venta_id=venta_id,
            producto_original=producto_original,
            cantidad=cantidad,
            estado=EstadoDeSustitucion.REGISTRADA,
            motivo=motivo,
        )

    def validar(
        self,
        alternativa_id: str,
        aprueba: bool,
        responsable_id: str,
        hoy: Optional[date] = None,
        observacion: str = "",
        rol_usuario: str = RolUsuario.RESPONSABLE_FARMACIA.value,
    ) -> None:
        """US-08 / BR-08: El Responsable de Farmacia evalúa y aprueba o rechaza la alternativa propuesta."""
        if rol_usuario != RolUsuario.RESPONSABLE_FARMACIA.value:
            raise UnauthorizedRoleAction("Solo el Responsable de Farmacia puede validar y autorizar una sustitución de medicamento (BR-08).")
        if not alternativa_id or not alternativa_id.strip():
            raise InvalidDomainData("Debe especificarse el producto alternativo propuesto.")
        if alternativa_id.strip() == self.producto_original:
            raise InvalidDomainData("El producto alternativo debe ser distinto al producto original sin existencia.")

        fecha = hoy or date.today()
        destino = (
            EstadoDeSustitucion.APROBADA_POR_FARMACIA
            if aprueba
            else EstadoDeSustitucion.RECHAZADA_POR_FARMACIA
        )
        self.estado = MaquinaEstadoSustitucion.transicionar(self.estado, destino)
        self.alternativa = alternativa_id.strip()
        self.decision_farmacia = DecisionDeFarmacia(
            aprobada=aprueba,
            responsable=responsable_id,
            fecha=fecha,
            observacion=observacion or ("Sustitución terapéutica equivalente aprobada" if aprueba else "La alternativa propuesta no procede"),
        )
        if not aprueba:
            self.eventos.append(
                SustitucionResuelta(
                    solicitud_id=self.id,
                    venta_id=self.venta_id,
                    resultado=self.estado.value,
                    ocurrido_en=fecha,
                )
            )

    def registrar_decision_del_cliente(self, acepta: bool, hoy: Optional[date] = None) -> None:
        """Secuencia 2 (CU-03): El cajero registra si el cliente acepta o rechaza la alternativa explicada."""
        fecha = hoy or date.today()
        destino = (
            EstadoDeSustitucion.ACEPTADA_POR_CLIENTE
            if acepta
            else EstadoDeSustitucion.RECHAZADA_POR_CLIENTE
        )
        self.estado = MaquinaEstadoSustitucion.transicionar(self.estado, destino)
        self.decision_cliente = DecisionDelCliente(acepta=acepta, fecha=fecha)
        self.eventos.append(
            SustitucionResuelta(
                solicitud_id=self.id,
                venta_id=self.venta_id,
                resultado=self.estado.value,
                ocurrido_en=fecha,
            )
        )

    def esta_aceptada(self) -> bool:
        return self.estado == EstadoDeSustitucion.ACEPTADA_POR_CLIENTE


# =====================================================================
# AGGREGATE 5: RECEPCIÓN DE MERCANCÍA (MAPA DE DOMINIO, ADR-002, CU-05, BR-06, BR-15, US-14)
# =====================================================================
@dataclass(frozen=True)
class LineaDeRecepcion:
    producto_id: str
    lote: NumeroDeLote
    caducidad: FechaDeCaducidad
    cantidad: Cantidad

    def __post_init__(self):
        if self.cantidad.valor <= 0:
            raise InvalidDomainData("La cantidad recibida en una línea de recepción debe ser mayor a cero.")


@dataclass
class RecepcionDeMercancia:
    """Aggregate Root que registra la entrada formal de lotes en Almacén (BR-15, RF-09, RF-10, US-14)."""
    id: str
    sucursal_id: str
    responsable: str
    fecha: date = field(default_factory=date.today)
    lineas: List[LineaDeRecepcion] = field(default_factory=list)
    eventos: List[EventoDeDominio] = field(default_factory=list)

    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise InvalidDomainData("El folio de recepción es obligatorio.")
        if not self.sucursal_id or not self.sucursal_id.strip():
            raise InvalidDomainData("La sucursal de recepción es obligatoria.")
        if not self.responsable or not self.responsable.strip():
            raise InvalidDomainData("El responsable de almacén es obligatorio (D-14).")

    def agregar_linea(
        self,
        producto_id: str,
        lote: NumeroDeLote,
        caducidad: FechaDeCaducidad,
        cantidad: Cantidad,
        hoy: Optional[date] = None,
    ) -> ResultadoDeOperacion[LineaDeRecepcion]:
        fecha_ref = hoy or self.fecha
        if caducidad.fue_alcanzada(fecha_ref):
            raise InvalidDomainData(
                f"No se puede recibir el lote {lote.codigo} porque su fecha de caducidad ({caducidad.fecha}) ya venció (BR-02, BR-15)."
            )
        linea = LineaDeRecepcion(
            producto_id=producto_id,
            lote=lote,
            caducidad=caducidad,
            cantidad=cantidad,
        )
        self.lineas.append(linea)
        self.eventos.append(
            MercanciaRecibida(
                recepcion_id=self.id,
                sucursal_id=self.sucursal_id,
                ocurrido_en=fecha_ref,
            )
        )
        return ResultadoDeOperacion.aceptar(linea)


# =====================================================================
# ENTIDADES DE CONTROL DE DIFERENCIAS Y RESURTIDO (BR-09, BR-10, BR-13, BR-14, US-10, US-11, US-12)
# =====================================================================
@dataclass
class DiferenciaDeInventario:
    """
    Modela una discrepancia entre el conteo físico en almacén y el inventario registrado (D-11, BR-13, RF-14, RF-15, US-10).
    Impide que se realicen ajustes directos sin revisión previa autorizada (RNF-08).
    """
    id: str
    producto_id: str
    sucursal_id: str
    numero_lote: NumeroDeLote
    cantidad_registrada: Cantidad
    cantidad_fisica: Cantidad
    motivo: str
    reportado_por: str
    fecha_reporte: date = field(default_factory=date.today)
    estado: EstadoDiferenciaInventario = EstadoDiferenciaInventario.PENDIENTE_REVISION
    revisado_por: Optional[str] = None
    observacion_revision: str = ""
    fecha_revision: Optional[date] = None

    def __post_init__(self):
        if self.cantidad_registrada.valor == self.cantidad_fisica.valor:
            raise InvalidDomainData("No existe diferencia entre la cantidad física y la cantidad registrada.")
        if not self.motivo or not self.motivo.strip():
            raise InvalidDomainData("Debe describirse el hallazgo o motivo de la diferencia de inventario.")
        if not self.reportado_por or not self.reportado_por.strip():
            raise InvalidDomainData("Debe indicarse el personal de almacén que reporta la diferencia.")

    @property
    def diferencia(self) -> int:
        return self.cantidad_fisica.valor - self.cantidad_registrada.valor

    def revisar_y_resolver(
        self,
        aprobar_ajuste: bool,
        revisado_por: str,
        observacion: str,
        hoy: Optional[date] = None,
        rol_usuario: str = RolUsuario.RESPONSABLE_FARMACIA.value,
    ) -> None:
        if rol_usuario == RolUsuario.CAJERO.value:
            raise UnauthorizedRoleAction("El cajero tiene prohibido modificar o autorizar ajustes de inventario (BR-14).")
        if rol_usuario not in (RolUsuario.RESPONSABLE_FARMACIA.value, RolUsuario.ADMINISTRACION.value):
            raise UnauthorizedRoleAction("Solo el Responsable de Farmacia o Administración pueden autorizar un ajuste de inventario (RF-15, RNF-08).")
        if not observacion or not observacion.strip():
            raise InvalidDomainData("Se requiere justificación/observación para autorizar o rechazar un ajuste de inventario (RNF-08).")

        destino = (
            EstadoDiferenciaInventario.AJUSTE_APROBADO
            if aprobar_ajuste
            else EstadoDiferenciaInventario.AJUSTE_RECHAZADO
        )
        self.estado = MaquinaEstadoDiferencia.transicionar(self.estado, destino)
        self.revisado_por = revisado_por.strip()
        self.observacion_revision = observacion.strip()
        self.fecha_revision = hoy or date.today()


@dataclass
class SolicitudDeResurtido:
    """
    Modela la necesidad y decisión de resurtido (D-12, BR-09, BR-10, RF-11, RF-12, US-11, US-12).
    Garantiza BR-10: no se generan órdenes de compra automáticas; requiere el análisis explícito del área de Compras.
    """
    id: str
    producto_id: str
    sucursal_id: str
    existencia_actual: int
    nivel_minimo: int
    estado: EstadoResurtido = EstadoResurtido.PENDIENTE_ANALISIS
    fecha_alerta: date = field(default_factory=date.today)
    analizado_por: Optional[str] = None
    cantidad_solicitada: int = 0
    justificacion: str = ""
    fecha_decision: Optional[date] = None

    def registrar_decision_compras(
        self,
        solicitar_abastecimiento: bool,
        analizado_por: str,
        cantidad_a_solicitar: int = 0,
        justificacion: str = "",
        hoy: Optional[date] = None,
        rol_usuario: str = RolUsuario.COMPRAS.value,
    ) -> None:
        if rol_usuario not in (RolUsuario.COMPRAS.value, RolUsuario.ADMINISTRACION.value):
            raise UnauthorizedRoleAction("Solo el área de Compras puede analizar y decidir sobre las solicitudes de resurtido (BR-10, RNF-07).")
        if not analizado_por or not analizado_por.strip():
            raise InvalidDomainData("Debe registrarse el responsable de Compras que analizó la necesidad de resurtido.")
        if solicitar_abastecimiento and cantidad_a_solicitar <= 0:
            raise InvalidDomainData("Cuando Compras aprueba un resurtido, la cantidad solicitada debe ser mayor a cero.")
        if not justificacion or not justificacion.strip():
            raise InvalidDomainData("Compras debe registrar la justificación del análisis de resurtido (BR-10).")

        destino = (
            EstadoResurtido.SOLICITADO_A_PROVEEDOR
            if solicitar_abastecimiento
            else EstadoResurtido.DESCARTADO
        )
        self.estado = MaquinaEstadoResurtido.transicionar(self.estado, destino)
        self.analizado_por = analizado_por.strip()
        self.cantidad_solicitada = cantidad_a_solicitar if solicitar_abastecimiento else 0
        self.justificacion = justificacion.strip()
        self.fecha_decision = hoy or date.today()

    def marcar_surtido(self, hoy: Optional[date] = None) -> None:
        self.estado = MaquinaEstadoResurtido.transicionar(self.estado, EstadoResurtido.SURTIDO)
        self.fecha_decision = hoy or date.today()
