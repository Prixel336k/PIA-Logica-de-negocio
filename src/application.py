from typing import Protocol, Optional, List, Any
from datetime import date
from decimal import Decimal
from src.domain import (
    Venta,
    InventarioDeProducto,
    Producto,
    SolicitudDeSustitucion,
    RecepcionDeMercancia,
    DiferenciaDeInventario,
    SolicitudDeResurtido,
    Dinero,
    Cantidad,
    NumeroDeLote,
    FechaDeCaducidad,
    EstadoValidacion,
    EstadoDelLote,
    EstadoDiferenciaInventario,
    EstadoResurtido,
    RolUsuario,
    EventoDeDominio,
    ExistenciaBajaDetectada,
    LoteProximoACaducarSpec,
    InvalidDomainData,
    InvalidOrderTransition,
    UnauthorizedRoleAction,
)


# =====================================================================
# PUERTOS / INTERFACES DE INFRAESTRUCTURA (ADR-005)
# =====================================================================
class RepositorioDeVentas(Protocol):
    def obtener_por_id(self, venta_id: str) -> Optional[Venta]: ...
    def guardar(self, venta: Venta) -> None: ...


class RepositorioDeInventarios(Protocol):
    def obtener_de(self, producto_id: str, sucursal_id: str) -> Optional[InventarioDeProducto]: ...
    def guardar(self, inventario: InventarioDeProducto) -> None: ...


class RepositorioDeProductos(Protocol):
    def obtener_por_id(self, producto_id: str) -> Optional[Producto]: ...
    def guardar(self, producto: Producto) -> None: ...
    def listar(self) -> List[Producto]: ...


class RepositorioDeSustituciones(Protocol):
    def obtener_por_id(self, solicitud_id: str) -> Optional[SolicitudDeSustitucion]: ...
    def guardar(self, solicitud: SolicitudDeSustitucion) -> None: ...
    def listar(self) -> List[SolicitudDeSustitucion]: ...


class RepositorioDeRecepciones(Protocol):
    def obtener_por_id(self, recepcion_id: str) -> Optional[RecepcionDeMercancia]: ...
    def guardar(self, recepcion: RecepcionDeMercancia) -> None: ...
    def listar(self) -> List[RecepcionDeMercancia]: ...


class RepositorioDeDiferencias(Protocol):
    def obtener_por_id(self, diferencia_id: str) -> Optional[DiferenciaDeInventario]: ...
    def guardar(self, diferencia: DiferenciaDeInventario) -> None: ...
    def listar(self) -> List[DiferenciaDeInventario]: ...


class RepositorioDeResurtidos(Protocol):
    def obtener_por_id(self, resurtido_id: str) -> Optional[SolicitudDeResurtido]: ...
    def guardar(self, resurtido: SolicitudDeResurtido) -> None: ...
    def listar(self) -> List[SolicitudDeResurtido]: ...


class ProcesadorDePagos(Protocol):
    def cobrar(self, monto: Dinero) -> bool: ...


class UnidadDeTrabajo(Protocol):
    def confirmar(self) -> None: ...
    def descartar(self) -> None: ...


class RelojDelNegocio(Protocol):
    def hoy(self) -> date: ...


class PublicadorDeEventos(Protocol):
    def publicar(self, evento: EventoDeDominio) -> None: ...


# =====================================================================
# CASOS DE USO / COMMANDS (ADR-003 Y ADR-004)
# =====================================================================
class IniciarVentaService:
    """Inicia una nueva operación de venta en captura en una sucursal (RF-01, US-01)."""
    def __init__(self, ventas_repo: RepositorioDeVentas, uow: UnidadDeTrabajo):
        self.ventas_repo = ventas_repo
        self.uow = uow

    def ejecutar(self, venta_id: str, cajero_id: str, sucursal_id: str) -> Venta:
        if not venta_id or not venta_id.strip():
            raise InvalidDomainData("El identificador de la venta es obligatorio.")
        if not cajero_id or not cajero_id.strip():
            raise InvalidDomainData("El identificador del cajero es obligatorio.")
        if not sucursal_id or not sucursal_id.strip():
            raise InvalidDomainData("La sucursal de la venta es obligatoria (D-05).")
        if self.ventas_repo.obtener_por_id(venta_id):
            raise InvalidOrderTransition(f"La venta {venta_id} ya existe en el sistema.")

        venta = Venta(id=venta_id.strip(), cajero_id=cajero_id.strip(), sucursal_id=sucursal_id.strip())
        self.ventas_repo.guardar(venta)
        self.uow.confirmar()
        return venta


class RegistrarProductoEnVentaService:
    """
    Orquesta CU-01 (US-01, US-02, US-04): Registrar productos disponibles en una venta.
    Verifica existencia (BR-01), que el lote no esté caducado (BR-02) ni retirado (BR-03),
    y detecta si el medicamento requiere validación especial (BR-04).
    """
    def __init__(
        self,
        ventas_repo: RepositorioDeVentas,
        inventarios_repo: RepositorioDeInventarios,
        productos_repo: Optional[RepositorioDeProductos],
        uow: UnidadDeTrabajo,
    ):
        self.ventas_repo = ventas_repo
        self.inventarios_repo = inventarios_repo
        self.productos_repo = productos_repo
        self.uow = uow

    def ejecutar(
        self,
        venta_id: str,
        producto_id: str,
        cantidad: int,
        hoy: date,
        numero_lote: Optional[str] = None,
        precio_unitario: Optional[Decimal] = None,
        requiere_validacion: Optional[bool] = None,
    ) -> Venta:
        venta = self.ventas_repo.obtener_por_id(venta_id)
        if not venta:
            raise ValueError("La venta especificada no existe.")

        cant_vo = Cantidad(cantidad)
        if cant_vo.valor <= 0:
            raise InvalidDomainData("La cantidad debe ser un entero estrictamente positivo (mayor a 0).")

        inv = self.inventarios_repo.obtener_de(producto_id, venta.sucursal_id)
        if not inv:
            raise InvalidDomainData(
                f"El producto {producto_id} no cuenta con inventario registrado en la sucursal {venta.sucursal_id} (BR-01). Puede consultar otra sucursal o solicitar sustitución."
            )

        if numero_lote:
            verif = inv.verificar_venta(numero_lote, cant_vo.valor, hoy)
            if not verif.aceptada:
                raise InvalidDomainData(verif.motivo)
            lote_seleccionado = NumeroDeLote(numero_lote)
        else:
            asignacion = inv.asignar_lote(cant_vo.valor, hoy)
            if not asignacion.aceptada or asignacion.valor is None:
                raise InvalidDomainData(asignacion.motivo)
            lote_seleccionado = asignacion.valor

        producto_cat = self.productos_repo.obtener_por_id(producto_id) if self.productos_repo else None
        if producto_cat:
            req_val = requiere_validacion if requiere_validacion is not None else producto_cat.requiere_validacion_especial()
            precio_vo = Dinero(precio_unitario) if precio_unitario is not None else producto_cat.precio
            venta.agregar_linea(
                producto_id=producto_cat.id,
                numero_lote=lote_seleccionado,
                cantidad=cant_vo,
                precio_unitario=precio_vo,
                requiere_validarcion=req_val,
                nombre_producto=producto_cat.nombre,
                requisito_descripcion=producto_cat.requisito.descripcion,
            )
        else:
            precio_vo = Dinero(precio_unitario if precio_unitario is not None else Decimal("100.00"))
            venta.agregar_linea(
                producto_id=producto_id,
                numero_lote=lote_seleccionado,
                cantidad=cant_vo,
                precio_unitario=precio_vo,
                requiere_validarcion=bool(requiere_validacion),
            )

        self.ventas_repo.guardar(venta)
        self.uow.confirmar()
        return venta


class ResolverValidacionEspecialService:
    """
    Orquesta CU-02 (US-03, BR-04, BR-05): El Responsable de Farmacia valida los requisitos
    de medicamentos sujetos a condiciones especiales.
    """
    def __init__(self, ventas_repo: RepositorioDeVentas, uow: UnidadDeTrabajo, publicador: Optional[PublicadorDeEventos] = None):
        self.ventas_repo = ventas_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(
        self,
        venta_id: str,
        linea_o_producto_id: str,
        aprueba: bool,
        responsable_id: str,
        rol_usuario: str,
        hoy: date,
        motivo: str = "",
    ) -> Venta:
        venta = self.ventas_repo.obtener_por_id(venta_id)
        if not venta:
            raise ValueError("La venta especificada no existe.")

        venta.resolver_validacion(
            identificador_linea_o_producto=linea_o_producto_id,
            aprueba=aprueba,
            responsable_id=responsable_id,
            hoy=hoy,
            motivo=motivo,
            rol_usuario=rol_usuario,
        )
        self.ventas_repo.guardar(venta)
        self.uow.confirmar()
        if self.publicador and venta.eventos:
            self.publicador.publicar(venta.eventos[-1])
        return venta


class SolicitarSustitucionService:
    """
    Orquesta CU-03 parte 1 (US-07, Secuencia 2): Registrar solicitud de sustitución cuando un producto no tiene existencia.
    """
    def __init__(
        self,
        ventas_repo: RepositorioDeVentas,
        sustituciones_repo: RepositorioDeSustituciones,
        uow: UnidadDeTrabajo,
    ):
        self.ventas_repo = ventas_repo
        self.sustituciones_repo = sustituciones_repo
        self.uow = uow

    def ejecutar(
        self,
        solicitud_id: str,
        venta_id: str,
        producto_original_id: str,
        cantidad: int,
        motivo: str = "Producto solicitado sin existencia disponible",
    ) -> SolicitudDeSustitucion:
        venta = self.ventas_repo.obtener_por_id(venta_id)
        if not venta:
            raise ValueError("La venta especificada no existe.")
        if not venta.esta_en_captura():
            raise InvalidOrderTransition("Solo se puede solicitar una sustitución para una venta que está en captura.")

        solicitud = SolicitudDeSustitucion.registrar(
            id=solicitud_id,
            venta_id=venta_id,
            producto_original=producto_original_id,
            cantidad=Cantidad(cantidad),
            motivo=motivo,
        )
        self.sustituciones_repo.guardar(solicitud)
        self.uow.confirmar()
        return solicitud


class ValidarSustitucionService:
    """
    Orquesta CU-03 parte 2 (US-08, BR-08, Secuencia 2): El Responsable de Farmacia valida y aprueba/rechaza la sustitución.
    """
    def __init__(
        self,
        sustituciones_repo: RepositorioDeSustituciones,
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
    ):
        self.sustituciones_repo = sustituciones_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(
        self,
        solicitud_id: str,
        alternativa_id: str,
        aprueba: bool,
        responsable_id: str,
        rol_usuario: str,
        hoy: date,
        observacion: str = "",
    ) -> SolicitudDeSustitucion:
        solicitud = self.sustituciones_repo.obtener_por_id(solicitud_id)
        if not solicitud:
            raise ValueError("La solicitud de sustitución especificada no existe.")

        solicitud.validar(
            alternativa_id=alternativa_id,
            aprueba=aprueba,
            responsable_id=responsable_id,
            hoy=hoy,
            observacion=observacion,
            rol_usuario=rol_usuario,
        )
        self.sustituciones_repo.guardar(solicitud)
        self.uow.confirmar()
        if self.publicador and solicitud.eventos:
            self.publicador.publicar(solicitud.eventos[-1])
        return solicitud


class RegistrarDecisionDelClienteService:
    """
    Orquesta CU-03 parte 3 (Secuencia 2 pasos 20-35, ADR-004):
    Registra si el cliente acepta o no la alternativa aprobada por farmacia.
    Si acepta, verifica que siga vendible, asigna lote y agrega la alternativa a la Venta en una sola UnidadDeTrabajo.
    """
    def __init__(
        self,
        sustituciones_repo: RepositorioDeSustituciones,
        ventas_repo: RepositorioDeVentas,
        inventarios_repo: RepositorioDeInventarios,
        productos_repo: Optional[RepositorioDeProductos],
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
    ):
        self.sustituciones_repo = sustituciones_repo
        self.ventas_repo = ventas_repo
        self.inventarios_repo = inventarios_repo
        self.productos_repo = productos_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(self, solicitud_id: str, acepta: bool, hoy: date) -> SolicitudDeSustitucion:
        solicitud = self.sustituciones_repo.obtener_por_id(solicitud_id)
        if not solicitud:
            raise ValueError("La solicitud de sustitución especificada no existe.")

        venta = self.ventas_repo.obtener_por_id(solicitud.venta_id)
        if not venta:
            raise ValueError("La venta asociada a la sustitución no existe.")

        solicitud.registrar_decision_del_cliente(acepta=acepta, hoy=hoy)

        if not acepta:
            self.sustituciones_repo.guardar(solicitud)
            self.uow.confirmar()
            if self.publicador and solicitud.eventos:
                self.publicador.publicar(solicitud.eventos[-1])
            return solicitud

        # Si el cliente acepta, asignar lote vendible del producto alternativo y agregarlo a la venta (Secuencia 2 pasos 27-33)
        alternativa_id = solicitud.alternativa
        if not alternativa_id:
            raise InvalidDomainData("La solicitud no tiene un producto alternativo validado por farmacia.")

        inv = self.inventarios_repo.obtener_de(alternativa_id, venta.sucursal_id)
        if not inv:
            raise InvalidDomainData(f"El producto alternativo {alternativa_id} no cuenta con inventario en la sucursal {venta.sucursal_id}.")

        asignacion = inv.asignar_lote(solicitud.cantidad.valor, hoy)
        if not asignacion.aceptada or asignacion.valor is None:
            raise InvalidDomainData(asignacion.motivo)

        prod_alt = self.productos_repo.obtener_por_id(alternativa_id) if self.productos_repo else None
        if prod_alt:
            venta.agregar_producto(prod_alt, asignacion.valor, solicitud.cantidad)
        else:
            venta.agregar_linea(
                producto_id=alternativa_id,
                numero_lote=asignacion.valor,
                cantidad=solicitud.cantidad,
                precio_unitario=Dinero(Decimal("150.00")),
            )

        self.sustituciones_repo.guardar(solicitud)
        self.ventas_repo.guardar(venta)
        self.uow.confirmar()
        if self.publicador and solicitud.eventos:
            self.publicador.publicar(solicitud.eventos[-1])
        return solicitud


class CompletarVentaService:
    """
    Orquesta el caso de uso CU-04 (Secuencia 1, US-17, BR-01..07, BR-09): Completar venta y actualizar inventario.
    Sigue estrictamente el orden de cobro: verifica -> procesa pago -> descuenta inventario -> confirma -> publica eventos (ADR-004).
    """
    def __init__(
        self,
        ventas_repo: RepositorioDeVentas,
        inventarios_repo: RepositorioDeInventarios,
        procesador_pagos: ProcesadorDePagos,
        uow: UnidadDeTrabajo,
        publicador_eventos: Optional[PublicadorDeEventos] = None,
        resurtidos_repo: Optional[RepositorioDeResurtidos] = None,
    ):
        self.ventas_repo = ventas_repo
        self.inventarios_repo = inventarios_repo
        self.procesador_pagos = procesador_pagos
        self.uow = uow
        self.publicador_eventos = publicador_eventos
        self.resurtidos_repo = resurtidos_repo

    def ejecutar(self, venta_id: str, hoy: date) -> str:
        venta = self.ventas_repo.obtener_por_id(venta_id)
        if not venta:
            raise ValueError("La venta especificada no existe.")

        if not venta.esta_en_captura():
            if venta.estado.value == "COMPLETADA":
                raise InvalidOrderTransition(f"La venta {venta.id} ya ha sido completada y no admite más cambios de estado.")
            raise InvalidOrderTransition(f"La venta {venta.id} fue rechazada previamente y no puede cobrarse.")

        # 1. Verificar si la venta puede cobrarse (valida recetas o requisitos especiales BR-04 y BR-05)
        venta.puede_cobrarse()

        # 2. Verificar la disponibilidad y vendibilidad de cada línea antes de tocar dinero o inventario (BR-01, BR-02, BR-03)
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
                raise ValueError(f"Existencia insuficiente en el lote {linea.numero_lote.codigo} (BR-01).")

        # 3. Procesar el pago con la pasarela externa (Secuencia 1 pasos 12-17)
        pago_exitoso = self.procesador_pagos.cobrar(venta.total)
        if not pago_exitoso:
            venta.rechazar("Pago rechazado por el procesador.", hoy=hoy)
            self.ventas_repo.guardar(venta)
            self.uow.confirmar()
            if self.publicador_eventos and venta.eventos:
                self.publicador_eventos.publicar(venta.eventos[-1])
            raise RuntimeError("El pago fue rechazado. La venta se marcó como rechazada y el inventario no se afectó.")

        # 4. Descontar inventarios, detectar existencia baja (BR-09) y completar venta (US-17)
        eventos_inventario: List[EventoDeDominio] = []
        for linea in venta.lineas:
            inv = self.inventarios_repo.obtener_de(linea.producto_id, venta.sucursal_id)
            eventos_previos = len(inv.eventos)
            inv.verificar_y_descontar(linea.numero_lote.codigo, linea.cantidad.valor, hoy)
            self.inventarios_repo.guardar(inv)
            nuevos_eventos = inv.eventos[eventos_previos:]
            eventos_inventario.extend(nuevos_eventos)

            # Si cayó por debajo del nivel mínimo, registrar necesidad de resurtido para Compras (BR-09, BR-10: sin compra automática)
            if self.resurtidos_repo and inv.esta_por_debajo_del_minimo(hoy):
                pendientes = [
                    r for r in self.resurtidos_repo.listar()
                    if r.producto_id == inv.producto_id
                    and r.sucursal_id == inv.sucursal_id
                    and r.estado == EstadoResurtido.PENDIENTE_ANALISIS
                ]
                if not pendientes:
                    alerta_id = f"RES-{inv.producto_id}-{inv.sucursal_id}-{len(self.resurtidos_repo.listar()) + 1:02d}"
                    self.resurtidos_repo.guardar(
                        SolicitudDeResurtido(
                            id=alerta_id,
                            producto_id=inv.producto_id,
                            sucursal_id=inv.sucursal_id,
                            existencia_actual=inv.existencia_vendible(hoy),
                            nivel_minimo=inv.nivel_minimo,
                            fecha_alerta=hoy,
                        )
                    )

        venta.completar(hoy=hoy)
        self.ventas_repo.guardar(venta)
        self.uow.confirmar()

        # 5. Publicar eventos de dominio tras confirmar la unidad de trabajo (ADR-004 paso 3)
        if self.publicador_eventos:
            if venta.eventos:
                self.publicador_eventos.publicar(venta.eventos[-1])
            for ev in eventos_inventario:
                self.publicador_eventos.publicar(ev)

        return "Venta completada y registrada exitosamente."


class RegistrarRecepcionDeMercanciaService:
    """
    Orquesta CU-05 (US-14, BR-06, BR-14, BR-15, RF-09, RF-10):
    El personal de Almacén registra la recepción de productos actualizando lote y fecha de caducidad en la sucursal.
    """
    def __init__(
        self,
        recepciones_repo: RepositorioDeRecepciones,
        inventarios_repo: RepositorioDeInventarios,
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
        resurtidos_repo: Optional[RepositorioDeResurtidos] = None,
    ):
        self.recepciones_repo = recepciones_repo
        self.inventarios_repo = inventarios_repo
        self.uow = uow
        self.publicador = publicador
        self.resurtidos_repo = resurtidos_repo

    def ejecutar(
        self,
        recepcion_id: str,
        sucursal_id: str,
        producto_id: str,
        numero_lote: str,
        caducidad: date,
        cantidad: int,
        responsable: str,
        rol_usuario: str,
        hoy: date,
        nivel_minimo_default: int = 5,
    ) -> RecepcionDeMercancia:
        if rol_usuario == RolUsuario.CAJERO.value:
            raise UnauthorizedRoleAction("El cajero tiene prohibido modificar o ingresar existencias de inventario directamente (BR-14).")
        if rol_usuario not in (RolUsuario.ALMACEN.value, RolUsuario.ADMINISTRACION.value):
            raise UnauthorizedRoleAction("Solo el personal de Almacén está autorizado para registrar la recepción de mercancía (RF-09, RNF-07).")

        recepcion = RecepcionDeMercancia(
            id=recepcion_id,
            sucursal_id=sucursal_id,
            responsable=responsable,
            fecha=hoy,
        )
        lote_vo = NumeroDeLote(numero_lote)
        cad_vo = FechaDeCaducidad(caducidad)
        cant_vo = Cantidad(cantidad)

        recepcion.agregar_linea(
            producto_id=producto_id,
            lote=lote_vo,
            caducidad=cad_vo,
            cantidad=cant_vo,
            hoy=hoy,
        )

        inv = self.inventarios_repo.obtener_de(producto_id, sucursal_id)
        if not inv:
            inv = InventarioDeProducto(
                producto_id=producto_id,
                sucursal_id=sucursal_id,
                nivel_minimo=nivel_minimo_default,
                lotes=[],
            )
        inv.registrar_entrada(lote_vo, caducidad, cant_vo, hoy)

        self.recepciones_repo.guardar(recepcion)
        self.inventarios_repo.guardar(inv)

        # Si había una solicitud de resurtido solicitada a proveedor y ya superó el mínimo, marcarla como surtida
        if self.resurtidos_repo and not inv.esta_por_debajo_del_minimo(hoy):
            for res in self.resurtidos_repo.listar():
                if res.producto_id == producto_id and res.sucursal_id == sucursal_id and res.estado == EstadoResurtido.SOLICITADO_A_PROVEEDOR:
                    res.marcar_surtido(hoy)
                    self.resurtidos_repo.guardar(res)

        self.uow.confirmar()
        if self.publicador and recepcion.eventos:
            self.publicador.publicar(recepcion.eventos[-1])
        return recepcion


class RetirarLoteService:
    """
    Orquesta US-06 / BR-03 / RF-04: El Responsable de Farmacia identifica y bloquea un lote como RETIRADO.
    """
    def __init__(
        self,
        inventarios_repo: RepositorioDeInventarios,
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
    ):
        self.inventarios_repo = inventarios_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(
        self,
        producto_id: str,
        sucursal_id: str,
        numero_lote: str,
        responsable: str,
        motivo: str,
        rol_usuario: str,
        hoy: date,
    ) -> InventarioDeProducto:
        if rol_usuario == RolUsuario.CAJERO.value:
            raise UnauthorizedRoleAction("El cajero no está autorizado para retirar o modificar lotes del inventario (BR-14).")
        if rol_usuario not in (RolUsuario.RESPONSABLE_FARMACIA.value, RolUsuario.ADMINISTRACION.value):
            raise UnauthorizedRoleAction("Solo el Responsable de Farmacia puede bloquear y retirar lotes de la operación (US-06, RNF-07).")

        inv = self.inventarios_repo.obtener_de(producto_id, sucursal_id)
        if not inv:
            raise ValueError(f"No existe inventario del producto {producto_id} en la sucursal {sucursal_id}.")

        inv.retirar_lote(numero_lote=numero_lote, responsable=responsable, motivo=motivo, hoy=hoy)
        self.inventarios_repo.guardar(inv)
        self.uow.confirmar()
        if self.publicador and inv.eventos:
            self.publicador.publicar(inv.eventos[-1])
        return inv


class RegistrarDiferenciaInventarioService:
    """
    Orquesta US-10 / BR-13 / BR-14 / RF-14:
    El personal de Almacén registra diferencias encontradas entre el inventario físico y el registrado para su revisión.
    """
    def __init__(
        self,
        inventarios_repo: RepositorioDeInventarios,
        diferencias_repo: RepositorioDeDiferencias,
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
    ):
        self.inventarios_repo = inventarios_repo
        self.diferencias_repo = diferencias_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(
        self,
        diferencia_id: str,
        producto_id: str,
        sucursal_id: str,
        numero_lote: str,
        cantidad_fisica: int,
        motivo: str,
        reportado_por: str,
        rol_usuario: str,
        hoy: date,
    ) -> DiferenciaDeInventario:
        if rol_usuario == RolUsuario.CAJERO.value:
            raise UnauthorizedRoleAction("El cajero tiene restringida cualquier modificación o reporte de ajuste directo sobre el inventario (BR-14).")
        if rol_usuario not in (RolUsuario.ALMACEN.value, RolUsuario.RESPONSABLE_FARMACIA.value, RolUsuario.ADMINISTRACION.value):
            raise UnauthorizedRoleAction("Solo el personal de Almacén o Supervisión puede registrar diferencias de conteo físico (US-10, RNF-07).")

        inv = self.inventarios_repo.obtener_de(producto_id, sucursal_id)
        if not inv:
            raise ValueError(f"No existe inventario para el producto {producto_id} en la sucursal {sucursal_id}.")

        lote = inv.obtener_lote(numero_lote)
        if not lote:
            raise ValueError(f"El lote {numero_lote} no existe en el inventario de la sucursal {sucursal_id}.")

        dif = DiferenciaDeInventario(
            id=diferencia_id,
            producto_id=producto_id,
            sucursal_id=sucursal_id,
            numero_lote=NumeroDeLote(numero_lote),
            cantidad_registrada=lote.cantidad,
            cantidad_fisica=Cantidad(cantidad_fisica),
            motivo=motivo,
            reportado_por=reportado_por,
            fecha_reporte=hoy,
        )
        self.diferencias_repo.guardar(dif)
        self.uow.confirmar()
        if self.publicador:
            self.publicador.publicar(
                EventoDeDominio(
                    nombre="DiferenciaDeInventarioRegistrada",
                    ocurrido_en=hoy,
                    detalles={
                        "diferencia_id": dif.id,
                        "producto_id": producto_id,
                        "sucursal_id": sucursal_id,
                        "lote": numero_lote,
                        "registrada": lote.cantidad.valor,
                        "fisica": cantidad_fisica,
                    },
                )
            )
        return dif


class RevisarDiferenciaInventarioService:
    """
    Orquesta BR-13, BR-14, RF-15 y RNF-08:
    Revisa una diferencia de inventario y, solo si es autorizada por el Responsable de Farmacia o Administración, aplica el ajuste auditable.
    """
    def __init__(
        self,
        diferencias_repo: RepositorioDeDiferencias,
        inventarios_repo: RepositorioDeInventarios,
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
    ):
        self.diferencias_repo = diferencias_repo
        self.inventarios_repo = inventarios_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(
        self,
        diferencia_id: str,
        aprobar_ajuste: bool,
        revisado_por: str,
        observacion: str,
        rol_usuario: str,
        hoy: date,
    ) -> DiferenciaDeInventario:
        dif = self.diferencias_repo.obtener_por_id(diferencia_id)
        if not dif:
            raise ValueError("El registro de diferencia de inventario no existe.")

        dif.revisar_y_resolver(
            aprobar_ajuste=aprobar_ajuste,
            revisado_por=revisado_por,
            observacion=observacion,
            hoy=hoy,
            rol_usuario=rol_usuario,
        )

        if aprobar_ajuste:
            inv = self.inventarios_repo.obtener_de(dif.producto_id, dif.sucursal_id)
            if not inv:
                raise ValueError("El inventario asociado a la diferencia no fue encontrado.")
            inv.aplicar_ajuste_autorizado(
                numero_lote=dif.numero_lote.codigo,
                nueva_cantidad_fisica=dif.cantidad_fisica.valor,
                responsable=revisado_por,
                motivo=observacion,
                hoy=hoy,
            )
            self.inventarios_repo.guardar(inv)
            if self.publicador and inv.eventos:
                self.publicador.publicar(inv.eventos[-1])

        self.diferencias_repo.guardar(dif)
        self.uow.confirmar()
        return dif


class AnalizarResurtidoService:
    """
    Orquesta US-11, US-12, BR-09, BR-10, RF-12:
    El área de Compras analiza manualmente la necesidad de resurtido (sin compras automáticas BR-10)
    y registra la decisión de abastecimiento.
    """
    def __init__(
        self,
        resurtidos_repo: RepositorioDeResurtidos,
        uow: UnidadDeTrabajo,
        publicador: Optional[PublicadorDeEventos] = None,
    ):
        self.resurtidos_repo = resurtidos_repo
        self.uow = uow
        self.publicador = publicador

    def ejecutar(
        self,
        resurtido_id: str,
        solicitar_abastecimiento: bool,
        analizado_por: str,
        cantidad_solicitada: int,
        justificacion: str,
        rol_usuario: str,
        hoy: date,
    ) -> SolicitudDeResurtido:
        resurtido = self.resurtidos_repo.obtener_por_id(resurtido_id)
        if not resurtido:
            raise ValueError("La solicitud o alerta de resurtido especificada no existe.")

        resurtido.registrar_decision_compras(
            solicitar_abastecimiento=solicitar_abastecimiento,
            analizado_por=analizado_por,
            cantidad_a_solicitar=cantidad_solicitada,
            justificacion=justificacion,
            hoy=hoy,
            rol_usuario=rol_usuario,
        )
        self.resurtidos_repo.guardar(resurtido)
        self.uow.confirmar()
        if self.publicador:
            self.publicador.publicar(
                EventoDeDominio(
                    nombre="DecisionDeResurtidoRegistrada",
                    ocurrido_en=hoy,
                    detalles={
                        "resurtido_id": resurtido.id,
                        "producto_id": resurtido.producto_id,
                        "sucursal_id": resurtido.sucursal_id,
                        "estado": resurtido.estado.value,
                        "cantidad_solicitada": resurtido.cantidad_solicitada,
                        "analizado_por": analizado_por,
                    },
                )
            )
        return resurtido


# =====================================================================
# QUERIES / CONSULTAS (CQRS BÁSICO - ADR-003 Y ADR-007)
# =====================================================================
class ConsultarDisponibilidadQuery:
    """
    Servicio de consulta pura (Query) que lee el estado del inventario por producto y sucursal (US-02, US-09).
    """
    def __init__(self, inventarios_repo: RepositorioDeInventarios, dias_proximidad: int = 30):
        self.inventarios_repo = inventarios_repo
        self.dias_proximidad = dias_proximidad

    def ejecutar(self, producto_id: str, sucursal_id: str, hoy: Optional[date] = None) -> dict:
        fecha_ref = hoy or date.today()
        inv = self.inventarios_repo.obtener_de(producto_id, sucursal_id)
        if not inv:
            return {
                "producto_id": producto_id,
                "sucursal_id": sucursal_id,
                "existencia_total": 0,
                "existencia_vendible": 0,
                "nivel_minimo": 0,
                "alerta_minimo": False,
                "disponible_para_venta": False,
                "lotes": [],
            }

        spec_proximo = LoteProximoACaducarSpec(self.dias_proximidad)
        return {
            "producto_id": inv.producto_id,
            "sucursal_id": inv.sucursal_id,
            "existencia_total": inv.existencia_total,
            "existencia_vendible": inv.existencia_vendible(fecha_ref),
            "nivel_minimo": inv.nivel_minimo,
            "alerta_minimo": inv.esta_por_debajo_del_minimo(),
            "disponible_para_venta": inv.existencia_vendible(fecha_ref) > 0,
            "lotes": [
                {
                    "numero": l.numero.codigo,
                    "cantidad": l.cantidad.valor,
                    "caducidad": str(l.caducidad),
                    "estado": l.estado.value,
                    "vendible": l.es_vendible(fecha_ref)[0] and l.cantidad.valor > 0,
                    "caducado": l.esta_caducado(fecha_ref),
                    "proximo_a_caducar": spec_proximo.is_satisfied_by(l, fecha_ref),
                    "motivo_bloqueo": l.es_vendible(fecha_ref)[1] if not l.es_vendible(fecha_ref)[0] else (l.motivo_retiro or ""),
                }
                for l in inv.lotes
            ],
        }


class ConsultarDisponibilidadPorSucursalQuery:
    """
    US-13 / BR-16 / REP-05 (ADR-007): Consulta la disponibilidad de un producto en todas las sucursales de FarmaExpress.
    """
    def __init__(self, inventarios_repo: Any, sucursales_catalogo: Optional[dict] = None):
        self.inventarios_repo = inventarios_repo
        self.sucursales_catalogo = sucursales_catalogo or {
            "SUC-01": "Sucursal Centro (Monterrey)",
            "SUC-02": "Sucursal San Nicolás (Norte)",
            "SUC-03": "Sucursal San Pedro (Sur)",
        }

    def ejecutar(self, producto_id: str, hoy: Optional[date] = None) -> dict:
        fecha_ref = hoy or date.today()
        detalle_query = ConsultarDisponibilidadQuery(self.inventarios_repo)
        sucursales_info = []
        for suc_id, suc_nombre in self.sucursales_catalogo.items():
            info = detalle_query.ejecutar(producto_id, suc_id, fecha_ref)
            sucursales_info.append(
                {
                    "sucursal_id": suc_id,
                    "nombre_sucursal": suc_nombre,
                    "existencia_total": info["existencia_total"],
                    "existencia_vendible": info["existencia_vendible"],
                    "nivel_minimo": info["nivel_minimo"],
                    "alerta_minimo": info["alerta_minimo"],
                    "tiene_disponibilidad": info["existencia_vendible"] > 0,
                    "lotes": info["lotes"],
                }
            )
        return {
            "producto_id": producto_id,
            "total_global_vendible": sum(s["existencia_vendible"] for s in sucursales_info),
            "sucursales_con_stock": [s["sucursal_id"] for s in sucursales_info if s["tiene_disponibilidad"]],
            "sucursales": sucursales_info,
        }


class ConsultarAlternativasDisponiblesQuery:
    """
    CU-03 / US-07 (Secuencia 2 pasos 9-10): Consulta productos alternativos con existencia vendible en la sucursal.
    """
    def __init__(self, productos_repo: RepositorioDeProductos, inventarios_repo: RepositorioDeInventarios):
        self.productos_repo = productos_repo
        self.inventarios_repo = inventarios_repo

    def ejecutar(self, producto_original_id: str, sucursal_id: str, hoy: Optional[date] = None) -> List[dict]:
        fecha_ref = hoy or date.today()
        original = self.productos_repo.obtener_por_id(producto_original_id)
        todos = self.productos_repo.listar()
        candidatos_ids = set(original.sustitutos_ids) if original and original.sustitutos_ids else {p.id for p in todos if p.id != producto_original_id}

        alternativas = []
        for prod in todos:
            if prod.id == producto_original_id or prod.id not in candidatos_ids:
                continue
            inv = self.inventarios_repo.obtener_de(prod.id, sucursal_id)
            vendible_cant = inv.existencia_vendible(fecha_ref) if inv else 0
            if vendible_cant > 0:
                lote_sugerido = inv.asignar_lote(1, fecha_ref).valor.codigo if inv and inv.asignar_lote(1, fecha_ref).valor else ""
                alternativas.append(
                    {
                        "producto_id": prod.id,
                        "nombre": prod.nombre,
                        "tipo": prod.tipo.value,
                        "precio": str(prod.precio.monto),
                        "existencia_vendible": vendible_cant,
                        "lote_sugerido": lote_sugerido,
                        "requiere_validacion_especial": prod.requiere_validacion_especial(),
                        "requisito_especial": prod.requisito.descripcion,
                    }
                )
        return alternativas


class ConsultarIndicadoresConsolidadosQuery:
    """
    US-16 / REP-01 a REP-07 / IND-01 a IND-05:
    Genera los reportes e indicadores ejecutivos consolidados para la Administración de FarmaExpress.
    """
    def __init__(
        self,
        inventarios_repo: Any,
        productos_repo: RepositorioDeProductos,
        diferencias_repo: RepositorioDeDiferencias,
        resurtidos_repo: RepositorioDeResurtidos,
        ventas_repo: Any,
        dias_proximidad: int = 30,
    ):
        self.inventarios_repo = inventarios_repo
        self.productos_repo = productos_repo
        self.diferencias_repo = diferencias_repo
        self.resurtidos_repo = resurtidos_repo
        self.ventas_repo = ventas_repo
        self.dias_proximidad = dias_proximidad

    def ejecutar(self, hoy: Optional[date] = None) -> dict:
        fecha_ref = hoy or date.today()
        productos_map = {p.id: p.nombre for p in self.productos_repo.listar()}
        inventarios: List[InventarioDeProducto] = (
            self.inventarios_repo.listar_todos()
            if hasattr(self.inventarios_repo, "listar_todos")
            else list(getattr(self.inventarios_repo, "inventarios", {}).values())
        )

        spec_proximo = LoteProximoACaducarSpec(self.dias_proximidad)

        rep_existencia_baja = []
        rep_proximos_caducar = []
        rep_caducados = []
        rep_lotes_retirados = []

        for inv in inventarios:
            nombre_prod = productos_map.get(inv.producto_id, inv.producto_id)
            vendible = inv.existencia_vendible(fecha_ref)
            if vendible < inv.nivel_minimo:
                rep_existencia_baja.append(
                    {
                        "producto_id": inv.producto_id,
                        "nombre": nombre_prod,
                        "sucursal_id": inv.sucursal_id,
                        "existencia_vendible": vendible,
                        "existencia_total": inv.existencia_total,
                        "nivel_minimo": inv.nivel_minimo,
                        "deficit": max(0, inv.nivel_minimo - vendible),
                    }
                )
            for lote in inv.lotes:
                if lote.estado == EstadoDelLote.RETIRADO:
                    rep_lotes_retirados.append(
                        {
                            "producto_id": inv.producto_id,
                            "nombre": nombre_prod,
                            "sucursal_id": inv.sucursal_id,
                            "lote": lote.numero.codigo,
                            "cantidad_bloqueada": lote.cantidad.valor,
                            "caducidad": str(lote.caducidad),
                            "motivo_retiro": lote.motivo_retiro or "Retiro preventivo de operación",
                            "retirado_por": lote.retirado_por or "RESP-FARMACIA",
                        }
                    )
                elif lote.esta_caducado(fecha_ref):
                    rep_caducados.append(
                        {
                            "producto_id": inv.producto_id,
                            "nombre": nombre_prod,
                            "sucursal_id": inv.sucursal_id,
                            "lote": lote.numero.codigo,
                            "cantidad_bloqueada": lote.cantidad.valor,
                            "caducidad": str(lote.caducidad),
                            "dias_vencido": (fecha_ref - lote.caducidad).days,
                        }
                    )
                elif spec_proximo.is_satisfied_by(lote, fecha_ref):
                    rep_proximos_caducar.append(
                        {
                            "producto_id": inv.producto_id,
                            "nombre": nombre_prod,
                            "sucursal_id": inv.sucursal_id,
                            "lote": lote.numero.codigo,
                            "cantidad": lote.cantidad.valor,
                            "caducidad": str(lote.caducidad),
                            "dias_restantes": (lote.caducidad - fecha_ref).days,
                        }
                    )

        diferencias = [
            {
                "id": d.id,
                "producto_id": d.producto_id,
                "nombre": productos_map.get(d.producto_id, d.producto_id),
                "sucursal_id": d.sucursal_id,
                "lote": d.numero_lote.codigo,
                "cantidad_registrada": d.cantidad_registrada.valor,
                "cantidad_fisica": d.cantidad_fisica.valor,
                "diferencia": d.diferencia,
                "motivo": d.motivo,
                "reportado_por": d.reportado_por,
                "estado": d.estado.value,
                "revisado_por": d.revisado_por,
                "observacion_revision": d.observacion_revision,
            }
            for d in self.diferencias_repo.listar()
        ]

        resurtidos = [
            {
                "id": r.id,
                "producto_id": r.producto_id,
                "nombre": productos_map.get(r.producto_id, r.producto_id),
                "sucursal_id": r.sucursal_id,
                "existencia_actual": r.existencia_actual,
                "nivel_minimo": r.nivel_minimo,
                "estado": r.estado.value,
                "analizado_por": r.analizado_por,
                "cantidad_solicitada": r.cantidad_solicitada,
                "justificacion": r.justificacion,
                "fecha_alerta": str(r.fecha_alerta),
            }
            for r in self.resurtidos_repo.listar()
        ]

        return {
            "politica_dias_proximidad_caducidad": self.dias_proximidad,
            "indicadores": {
                "IND_01_productos_bajo_nivel_minimo": len(rep_existencia_baja),
                "IND_02_productos_proximos_a_caducar": len(rep_proximos_caducar),
                "IND_03_incidencias_productos_caducados": len(rep_caducados),
                "IND_04_lotes_retirados_bloqueados": len(rep_lotes_retirados),
                "IND_05_diferencias_de_inventario": len(diferencias),
            },
            "reportes": {
                "REP_01_existencia_baja": rep_existencia_baja,
                "REP_02_proximos_a_caducar": rep_proximos_caducar,
                "REP_03_productos_caducados": rep_caducados,
                "REP_04_lotes_retirados": rep_lotes_retirados,
                "REP_06_diferencias_inventario": diferencias,
                "REP_07_necesidades_resurtido": resurtidos,
            },
        }
