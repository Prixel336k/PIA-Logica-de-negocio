FarmaExpress - Sistema de Gestion Farmaceutica

Proyecto Integrador de Aprendizaje (PIA) -EQ10

Descripcion del Proyecto

FarmaExpress es un sistema backend robusto disenado bajo los principios de Clean Architecture y Domain-Driven Design (DDD) para optimizar el control de inventarios, lotes con caducidades y el procesamiento seguro de ventas en sucursales farmaceuticas.

El sistema implementa patrones transaccionales estrictos, manejo centralizado de excepciones HTTP (404, 409, 422) y simulacion de pasarelas de pago.

Arquitectura del Sistema

El proyecto esta desacoplado en capas independientes:

Dominio (src/domain.py): Contiene las entidades de negocio puras, Value Objects (Dinero, Cantidad, NumeroDeLote) y reglas invariantes (ej. validacion de lotes caducados o cantidades negativas).

Aplicacion (src/application.py): Casos de uso (CompletarVentaService, ConsultarDisponibilidadQuery) que coordinan las transacciones de negocio.

Infraestructura (src/infrastructure.py): Repositorios en memoria y adaptadores para persistencia y pasarela de pagos.

API REST (src/api.py): Interfaz web construida con FastAPI, validacion estricta con Pydantic y documentacion interactiva automatica.

Tecnologias y Librerias Utilizadas

Python 3.11+

FastAPI y Uvicorn (Framework web asincrono y servidor ASGI)

Pydantic v2 (Validacion de esquemas de datos)

Pytest y Pytest-Cov (Pruebas unitarias/integracion y medicion de cobertura)

Docker y Docker Compose (Contenedorizacion para portabilidad en equipo)

Instrucciones de Instalacion y Ejecucion Local

 Clonar el repositorio y activar el entorno virtual

git clone <https://github.com/Prixel336k/PIA-Logica-de-negocio>
cd PIA-EQ10

Crear y activar entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1


 Instalar dependencias

pip install -r requirements.txt


 Ejecutar la API en modo de desarrollo

uvicorn src.api:app --reload


Una vez encendida, abre tu navegador en:

Documentacion Interactiva (Swagger UI): http://localhost:8000/docs

Documentacion Alternativa (Redoc): http://localhost:8000/redoc

Pruebas Automatizadas y Cobertura

El proyecto cuenta con una suite completa de pruebas (dominio, aplicacion y API) que superan el 85% de cobertura exigido por la rubrica.

Para ejecutar todas las pruebas y generar el reporte de cobertura en terminal, ejecuta:

python -m pytest --cov=src --cov-report=term-missing


Ejecucion mediante Docker (Recomendado para Equipos)

Para garantizar la portabilidad absoluta sin importar el sistema operativo, puedes levantar toda la aplicacion en un contenedor aislado:

Asegurate de tener Docker Desktop abierto.

Ejecuta el siguiente comando en la raiz del proyecto:

docker compose up --build


El servicio estara disponible de inmediato en http://localhost:8000/docs.

Para detener el contenedor, presiona Ctrl + C en tu terminal.

Estructura del Repositorio

PIA-EQ10/
├── .github/workflows/ci.yml   # Pipeline de integracion continua (CI) en GitHub Actions
├── docs/                      # Documentacion BRD y registros ADR
├── src/                       # Codigo fuente (Clean Architecture)
│   ├── __init__.py
│   ├── domain.py              # Reglas de negocio y entidades
│   ├── application.py         # Casos de uso
│   ├── infrastructure.py      # Repositorios y adaptadores
│   └── api.py                 # Endpoints FastAPI y manejo de errores
├── tests/                     # Pruebas automatizadas (pytest)
│   ├── test_domain.py
│   ├── test_application.py
│   └── test_api.py
├── .env.example               # Variables de entorno de ejemplo
├── Dockerfile                 # Configuracion de la imagen Docker
├── docker-compose.yml         # Orquestacion de contenedores
├── requirements.txt           # Dependencias del proyecto
└── README.md                 
