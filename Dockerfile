#Usamos una imagen oficial de Python ligera
FROM python:3.11-slim

#Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos e instalamos las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#Copiamos el código fuente y las pruebas
COPY src/ ./src/
COPY tests/ ./tests/

#Exponemos el puerto donde corre FastAPI
EXPOSE 8000

#Comando por defecto para arrancar la API en producción
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]