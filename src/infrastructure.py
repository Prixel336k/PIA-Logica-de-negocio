import os
import json
from datetime import date, datetime, timezone
from typing import Optional, Dict, Tuple, List
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

from src.domain import (
    Venta,
    InventarioDeProducto,
    Producto,
    SolicitudDeSustitucion,
    RecepcionDeMercancia,
    DiferenciaDeInventario,
    SolicitudDeResurtido,
    Dinero,
    EventoDeDominio,
)
from src.application import (
    RepositorioDeVentas,
    RepositorioDeInventarios,
    RepositorioDeProductos,
    RepositorioDeSustituciones,
    RepositorioDeRecepciones,
    RepositorioDeDiferencias,
    RepositorioDeResurtidos,
    ProcesadorDePagos,
    UnidadDeTrabajo,
    RelojDelNegocio,
    PublicadorDeEventos,
)

Base = declarative_base()


# =====================================================================
# MODELOS SQLALCHEMY PARA AUDITORÍA Y PERSISTENCIA (REQ_PIA DB + RNF-03/RNF-08)
# =====================================================================
class BitacoraEventoModel(Base):
    __tablename__ = "farmaexpress_bitacora_eventos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(120), nullable=False)
    referencia_id = Column(String(100), nullable=True)
    fecha = Column(String(40), nullable=False)
    detalles_json = Column(Text, nullable=False)
    creado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def crear_session_factory(database_url: Optional[str] = None):
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./farmaexpress.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    try:
        engine = create_engine(url, connect_args=connect_args)
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)
    except Exception:
        # Fallback seguro a SQLite en memoria si PostgreSQL externo no está levantado en entorno local
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autoflush=False, autocommit=False)


# =====================================================================
# REPOSITORIOS EN MEMORIA (ADR-005)
# =====================================================================
class MemoriaRepositorioDeVentas(RepositorioDeVentas):
    """Implementación en memoria del repositorio de ventas para pruebas y ejecución (ADR-005)."""
    def __init__(self):
        self.ventas: Dict[str, Venta] = {}

    def obtener_por_id(self, venta_id: str) -> Optional[Venta]:
        return self.ventas.get(venta_id)

    def guardar(self, venta: Venta) -> None:
        self.ventas[venta.id] = venta

    def listar(self) -> List[Venta]:
        return list(self.ventas.values())


class MemoriaRepositorioDeInventarios(RepositorioDeInventarios):
    """Implementación en memoria del inventario de productos por sucursal (ADR-002, ADR-005)."""
    def __init__(self):
        # La clave es una tupla: (producto_id, sucursal_id)
        self.inventarios: Dict[Tuple[str, str], InventarioDeProducto] = {}

    def obtener_de(self, producto_id: str, sucursal_id: str) -> Optional[InventarioDeProducto]:
        return self.inventarios.get((producto_id, sucursal_id))

    def guardar(self, inventario: InventarioDeProducto) -> None:
        self.inventarios[(inventario.producto_id, inventario.sucursal_id)] = inventario

    def listar_todos(self) -> List[InventarioDeProducto]:
        return list(self.inventarios.values())

    def listar_por_sucursal(self, sucursal_id: str) -> List[InventarioDeProducto]:
        return [inv for ( _, suc), inv in self.inventarios.items() if suc == sucursal_id]


class MemoriaRepositorioDeProductos(RepositorioDeProductos):
    """Repositorio del catálogo de productos (Medicamentos y Cuidado Personal)."""
    def __init__(self):
        self.productos: Dict[str, Producto] = {}

    def obtener_por_id(self, producto_id: str) -> Optional[Producto]:
        return self.productos.get(producto_id)

    def guardar(self, producto: Producto) -> None:
        self.productos[producto.id] = producto

    def listar(self) -> List[Producto]:
        return list(self.productos.values())


class MemoriaRepositorioDeSustituciones(RepositorioDeSustituciones):
    """Repositorio de solicitudes de sustitución (CU-03, BR-08)."""
    def __init__(self):
        self.sustituciones: Dict[str, SolicitudDeSustitucion] = {}

    def obtener_por_id(self, solicitud_id: str) -> Optional[SolicitudDeSustitucion]:
        return self.sustituciones.get(solicitud_id)

    def guardar(self, solicitud: SolicitudDeSustitucion) -> None:
        self.sustituciones[solicitud.id] = solicitud

    def listar(self) -> List[SolicitudDeSustitucion]:
        return list(self.sustituciones.values())


class MemoriaRepositorioDeRecepciones(RepositorioDeRecepciones):
    """Repositorio de recepciones de mercancía en Almacén (CU-05, BR-15)."""
    def __init__(self):
        self.recepciones: Dict[str, RecepcionDeMercancia] = {}

    def obtener_por_id(self, recepcion_id: str) -> Optional[RecepcionDeMercancia]:
        return self.recepciones.get(recepcion_id)

    def guardar(self, recepcion: RecepcionDeMercancia) -> None:
        self.recepciones[recepcion.id] = recepcion

    def listar(self) -> List[RecepcionDeMercancia]:
        return list(self.recepciones.values())


class MemoriaRepositorioDeDiferencias(RepositorioDeDiferencias):
    """Repositorio de diferencias entre inventario físico y registrado (BR-13, RF-14, RF-15)."""
    def __init__(self):
        self.diferencias: Dict[str, DiferenciaDeInventario] = {}

    def obtener_por_id(self, diferencia_id: str) -> Optional[DiferenciaDeInventario]:
        return self.diferencias.get(diferencia_id)

    def guardar(self, diferencia: DiferenciaDeInventario) -> None:
        self.diferencias[diferencia.id] = diferencia

    def listar(self) -> List[DiferenciaDeInventario]:
        return list(self.diferencias.values())


class MemoriaRepositorioDeResurtidos(RepositorioDeResurtidos):
    """Repositorio de alertas y solicitudes de resurtido para Compras (BR-09, BR-10)."""
    def __init__(self):
        self.resurtidos: Dict[str, SolicitudDeResurtido] = {}

    def obtener_por_id(self, resurtido_id: str) -> Optional[SolicitudDeResurtido]:
        return self.resurtidos.get(resurtido_id)

    def guardar(self, resurtido: SolicitudDeResurtido) -> None:
        self.resurtidos[resurtido.id] = resurtido

    def listar(self) -> List[SolicitudDeResurtido]:
        return list(self.resurtidos.values())


# =====================================================================
# PUERTOS Y ADAPTADORES DE INFRAESTRUCTURA (ADR-004 Y ADR-005)
# =====================================================================
class SimuladorProcesadorDePagos(ProcesadorDePagos):
    """Adaptador simulado para la pasarela de pagos externa (evita cobros reales)."""
    def __init__(self, respuesta_exitosa: bool = True):
        self.respuesta_exitosa = respuesta_exitosa

    def cobrar(self, monto: Dinero) -> bool:
        return self.respuesta_exitosa


class MemoriaUnidadDeTrabajo(UnidadDeTrabajo):
    """Simula la Unit of Work (todo o nada) para los agregados (ADR-004)."""
    def __init__(self):
        self.cometido = False
        self.descartado = False

    def confirmar(self) -> None:
        self.cometido = True

    def descartar(self) -> None:
        self.descartado = True


class RelojDelSistema(RelojDelNegocio):
    """Puerto RelojDelNegocio (ADR-005, ADR-006) que provee la fecha actual o una fecha simulada para pruebas."""
    def __init__(self, fecha_fija: Optional[date] = None):
        self.fecha_fija = fecha_fija

    def hoy(self) -> date:
        return self.fecha_fija or date.today()


class MemoriaPublicadorDeEventos(PublicadorDeEventos):
    """
    Adaptador de PublicadorDeEventos y NotificadorACompras (Secuencia 1 y ADR-005).
    Conserva el historial auditable en memoria y en base de datos SQLAlchemy (RNF-03, RNF-08).
    """
    def __init__(self, session_factory=None):
        self.eventos_publicados: List[EventoDeDominio] = []
        self.alertas_compras: List[dict] = []
        self.session_factory = session_factory

    def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos_publicados.append(evento)
        if evento.nombre == "ExistenciaBajaDetectada":
            self.alertas_compras.append(
                {
                    "evento": evento.nombre,
                    "fecha": str(evento.ocurrido_en),
                    "mensaje": (
                        f"Alerta para Compras (BR-09): El producto {evento.detalles.get('producto_id')} "
                        f"en {evento.detalles.get('sucursal_id')} tiene existencia {evento.detalles.get('existencia_actual')} "
                        f"(debajo del mínimo de {evento.detalles.get('nivel_minimo')}). Requiere análisis manual (BR-10)."
                    ),
                    "detalles": evento.detalles,
                }
            )
        if self.session_factory is not None:
            try:
                with self.session_factory() as session:
                    registro = BitacoraEventoModel(
                        nombre=evento.nombre,
                        referencia_id=evento.venta_id or evento.detalles.get("producto_id", ""),
                        fecha=str(evento.ocurrido_en),
                        detalles_json=json.dumps(evento.detalles, ensure_ascii=False),
                    )
                    session.add(registro)
                    session.commit()
            except Exception:
                pass

    def listar_historial(self) -> List[dict]:
        return [
            {
                "indice": idx + 1,
                "evento": ev.nombre,
                "venta_id": ev.venta_id,
                "fecha": str(ev.ocurrido_en),
                "detalles": ev.detalles,
            }
            for idx, ev in enumerate(reversed(self.eventos_publicados))
        ]
