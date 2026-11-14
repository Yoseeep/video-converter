# Imagen base ligera con Python 3.12
FROM python:3.12-slim

# Evitar prompts interactivos durante la instalación
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# Instalar FFmpeg y librerías necesarias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar el código de la aplicación
COPY . /app

# Crear directorios temporales de trabajo
RUN mkdir -p /app/uploads /app/converted

# Puerto por defecto (Render, Railway y Cloud Run sobreescriben la variable PORT automáticamente)
ENV PORT=8080
EXPOSE 8080

# Iniciar servidor
CMD ["python3", "server.py"]
