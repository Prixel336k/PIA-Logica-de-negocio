# Usamos una imagen oficial de Python ligera
FROM python:3.11-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos e instalamos las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código fuente (incluyendo la interfaz HTML/CSS en src/static) y las pruebas
COPY src/ ./src/
COPY tests/ ./tests/

# Exponemos el puerto donde corre FastAPI (compatible con Render $PORT y local 8000)
EXPOSE 8000

# Comando por defecto para arrancar la API e interfaz web en producción (Render / Docker)
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
