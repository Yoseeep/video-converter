# 🎬 Conversor de Video Multi-Archivo Web (FFmpeg)

Una aplicación web moderna, rápida y 100% privada para convertir múltiples archivos de video de forma masiva o individual entre diferentes formatos (por ejemplo, **MPG a MP4**, MKV a MP4, AVI a WEBM, etc.).

---

## ✨ Características Principales

- **Carga Múltiple (Batch Drag & Drop)**: Arrastra varios archivos de video o selecciónalos desde el explorador.
- **Formato por Lote o Individual**:
  - Puedes definir un formato de salida global (por ejemplo, *Convertir todos a MP4*).
  - O personalizar el formato destino para cada video de manera individual.
- **Formatos Soportados**:
  - **Entrada**: MPG, MPEG, MP4, MKV, AVI, MOV, WEBM, FLV, WMV, VOB, TS, 3GP, M4V, etc.
  - **Salida**: MP4 (H.264 / AAC universal con `+faststart`), MKV, WEBM (VP9), MOV, AVI, MPG, GIF animado, MP3 (extraer audio), WAV, M4A.
- **Monitoreo en Tiempo Real**:
  - Barra de progreso de subida por streaming para cada archivo.
  - Barra de progreso real de codificación con FFmpeg (`out_time_us`).
- **Descargas Cómodas**:
  - Descarga individual por archivo con cálculo de peso final y porcentaje de reducción de tamaño.
  - Botón **"Descargar Todo (.ZIP)"** para obtener todas las conversiones en un solo archivo comprimido.
- **Previsualización Integrada**: Reproductor HTML5 incorporado para visualizar los videos convertidos sin salir del navegador.
- **Ajustes Avanzados**:
  - Calidad de video: Equilibrada (CRF 23), Alta Calidad (CRF 19), Archivo Comprimido (CRF 28).
  - Ajuste de resolución: Original, 1080p, 720p, 480p.
  - Opciones de audio: Normal o Silenciar (Mute).
- **100% Privado y Local**:
  - Sin subir tus videos a servicios de terceros ni límites de tamaño en la nube. Todo el proceso ocurre en tu propio equipo.
  - Cero dependencias externas de Python: desarrollado usando la librería estándar de Python 3 y el binario nativo de FFmpeg.

---

## 🚀 Cómo Iniciar la Aplicación

1. Abre una terminal en esta carpeta:
   ```bash
   cd /Users/josema/Downloads/video_converter_web
   ```

2. Ejecuta el servidor:
   ```bash
   python3 server.py
   ```

3. Abre tu navegador web en:
   👉 **[http://localhost:8080](http://localhost:8080)**

*(Si el puerto 8080 estuviera ocupado, el servidor detectará automáticamente el siguiente puerto libre disponible).*

---

## 📁 Estructura del Proyecto

```
video_converter_web/
├── server.py             # Servidor HTTP multi-hilo en Python con API REST y gestión de FFmpeg
├── Dockerfile            # Contenedor Docker listo para producción con Python y FFmpeg
├── docker-compose.yml    # Configuración para despliegue rápido con Docker
├── .dockerignore         # Exclusiones de construcción Docker
├── templates/
│   └── index.html        # Interfaz web responsiva con drag & drop y reproductor de video
├── static/
│   ├── css/
│   │   └── style.css     # Estilos modernos con modo oscuro y animaciones fluidas
│   └── js/
│       └── app.js        # Lógica del cliente: colas de subida, sondeo en tiempo real y descarga
├── uploads/              # Carpeta temporal donde se reciben los videos subidos
├── converted/            # Carpeta donde se guardan los videos convertidos
└── README.md             # Esta documentación
```

---

## 🌐 Cómo Desplegarlo en Internet

Para que una aplicación de conversión de video funcione en internet, el servidor necesita dos cosas indispensables:
1. **FFmpeg instalado en el sistema**.
2. **Capacidad de procesamiento (CPU y disco)** para recibir videos y codificarlos.

Por este motivo, las plataformas serverless estáticas (como Vercel o Netlify estándar) no son aptas. A continuación tienes las **3 mejores opciones**:

### Opción 1: Render o Railway (La más sencilla y recomendada con Docker)

Tanto **Render** como **Railway** permiten desplegar contenedores Docker de forma muy sencilla conectando tu repositorio de GitHub:

1. **Sube tu proyecto a GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   git push -u origin main
   ```
2. **En Render (render.com)**:
   - Crea una cuenta y pulsa en **"New +"** &rarr; **"Web Service"**.
   - Conecta tu repositorio de GitHub.
   - En **Environment**, selecciona **Docker** (detectará automáticamente el `Dockerfile` que ya te he creado).
   - Elige el plan gratuito o básico y pulsa **Deploy**.
   - En 2 minutos tendrás una URL pública HTTPS tipo: `https://mi-conversor.onrender.com`.

3. **En Railway (railway.app)**:
   - Crea un nuevo proyecto desde tu repositorio de GitHub.
   - Detectará el `Dockerfile` y comenzará a construirlo automáticamente.

---

### Opción 2: En un VPS propio (Hetzner, DigitalOcean, Linode, AWS Lightsail)

Es la mejor opción si planeas convertir videos largos o muy pesados, ya que dispones de núcleos de CPU dedicados y almacenamiento amplio por solo 4-5 €/mes.

1. Conéctate a tu servidor Linux por SSH:
   ```bash
   ssh root@ip_de_tu_servidor
   ```
2. Clona el repositorio o sube los archivos.
3. Inicia la aplicación con Docker Compose en un solo comando:
   ```bash
   docker compose up -d --build
   ```
4. ¡Listo! La web estará activa en `http://ip_de_tu_servidor:8080`. Puedes colocarle un dominio y SSL gratis con Nginx + Certbot.

---

### Opción 3: Compartir temporalmente a Internet desde tu Mac (Sin coste ni servidores)

Si solo quieres compartir la página con amigos, clientes o compañeros de inmediato sin configurar ningún hosting:

- **Con Cloudflare Tunnel (gratis y seguro)**:
  ```bash
  brew install cloudflared
  cloudflared tunnel --url http://localhost:8080
  ```
  Te dará al instante una URL pública HTTPS tipo `https://xxxxx.trycloudflare.com` que cualquiera en internet podrá abrir mientras tengas tu Mac encendido.

- **Con ngrok**:
  ```bash
  ngrok http 8080
  ```

