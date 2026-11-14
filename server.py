#!/usr/bin/env python3
"""
Servidor web de conversión de video multi-archivo con FFmpeg.
Desarrollado en Python puro (librería estándar, sin dependencias externas).
Optimizado para bajo consumo de RAM/CPU en entornos como Render, Railway y VPS.
"""

import os
import sys
import json
import time
import uuid
import shutil
import urllib.parse
import subprocess
import threading
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import io
import zipfile

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
CONVERTED_DIR = BASE_DIR / "converted"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
TASKS_FILE = UPLOADS_DIR / "tasks.json"

UPLOADS_DIR.mkdir(exist_ok=True)
CONVERTED_DIR.mkdir(exist_ok=True)

# Estado de tareas en memoria (protegido por un RLock reentrante)
tasks_lock = threading.RLock()
tasks = {}

# 1 conversión simultánea para no saturar memoria RAM en Render (límite 512MB)
MAX_WORKERS = int(os.environ.get("MAX_CONVERSIONS", 1))
conversion_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".gif": "image/gif",
    ".zip": "application/zip",
}

def save_tasks_to_disk():
    """Persiste el estado de las tareas en disco para resistir reinicios del contenedor."""
    try:
        with tasks_lock:
            data = list(tasks.values())
        tmp_file = UPLOADS_DIR / "tasks.json.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_file.replace(TASKS_FILE)
    except Exception as e:
        print(f"[Storage] Error guardando tareas: {e}", file=sys.stderr)

def load_tasks_from_disk():
    """Recupera tareas guardadas al reiniciar el servidor."""
    if not TASKS_FILE.exists():
        return
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        with tasks_lock:
            for item in data:
                # Si el contenedor se reinició durante la conversión o subida
                if item.get("status") in ["converting", "uploading"]:
                    if Path(item.get("input_path", "")).exists():
                        item["status"] = "queued"
                        item["progress"] = 0
                    else:
                        item["status"] = "error"
                        item["error_message"] = "Archivo no disponible tras reinicio"
                tasks[item["id"]] = item
        print(f"[Storage] Cargadas {len(data)} tareas guardadas previamente.")
    except Exception as e:
        print(f"[Storage] Error cargando tareas de disco: {e}", file=sys.stderr)

def get_media_duration(file_path):
    """Obtiene la duración del archivo en segundos usando ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception as e:
        print(f"[FFprobe] Error obteniendo duración: {e}", file=sys.stderr)
    return None

def build_ffmpeg_cmd(input_path, output_path, target_format, options):
    """
    Genera la lista de argumentos para FFmpeg según formato y opciones.
    Optimizado con '-threads 2', '-preset veryfast' y buffers ajustados para no exceder 512MB RAM.
    """
    target_format = target_format.lower()
    quality = options.get("quality", "normal")       # high, normal, compact
    resolution = options.get("resolution", "original") # original, 1080p, 720p, 480p
    audio_mode = options.get("audio", "default")      # default, mute, copy

    # Mapeo de CRF según calidad para H.264 / VP9
    crf_map = {
        "high": "19",
        "normal": "23",
        "compact": "28"
    }
    crf = crf_map.get(quality, "23")

    # Limitar hilos a 2 en decodificación para evitar picos de memoria en la nube
    cmd = ["ffmpeg", "-y", "-threads", "2", "-i", str(input_path)]

    # Filtros de video
    video_filters = []
    if resolution == "1080p":
        video_filters.append("scale=-2:1080")
    elif resolution == "720p":
        video_filters.append("scale=-2:720")
    elif resolution == "480p":
        video_filters.append("scale=-2:480")

    # Audio mute
    if audio_mode == "mute":
        cmd.append("-an")

    # Configuración por formato de destino con presets ligeros
    if target_format == "mp4":
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", crf,
            "-pix_fmt", "yuv420p",
            "-threads", "2",
            "-x264-params", "rc-lookahead=10:sync-lookahead=10:threads=2",
            "-max_muxing_queue_size", "1024"
        ])
        if audio_mode != "mute":
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        cmd.extend(["-movflags", "+faststart"])

    elif target_format == "webm":
        cmd.extend([
            "-c:v", "libvpx-vp9",
            "-b:v", "0",
            "-crf", "30",
            "-threads", "2",
            "-speed", "4",
            "-tile-columns", "1",
            "-max_muxing_queue_size", "1024"
        ])
        if audio_mode != "mute":
            cmd.extend(["-c:a", "libopus", "-b:a", "128k"])

    elif target_format == "mkv":
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", crf,
            "-threads", "2",
            "-x264-params", "rc-lookahead=10:sync-lookahead=10:threads=2",
            "-max_muxing_queue_size", "1024"
        ])
        if audio_mode != "mute":
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

    elif target_format == "avi":
        cmd.extend(["-c:v", "mpeg4", "-qscale:v", "3", "-threads", "2"])
        if audio_mode != "mute":
            cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])

    elif target_format == "mov":
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", crf,
            "-pix_fmt", "yuv420p",
            "-threads", "2",
            "-x264-params", "rc-lookahead=10:sync-lookahead=10:threads=2",
            "-max_muxing_queue_size", "1024"
        ])
        if audio_mode != "mute":
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

    elif target_format in ["mpg", "mpeg"]:
        cmd.extend(["-c:v", "mpeg2video", "-qscale:v", "3", "-threads", "2"])
        if audio_mode != "mute":
            cmd.extend(["-c:a", "mp2", "-b:a", "192k"])

    elif target_format == "gif":
        filter_str = "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd.extend(["-vf", filter_str, "-threads", "2"])
        cmd.append("-an")
        video_filters = []

    elif target_format == "mp3":
        cmd.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])

    elif target_format == "wav":
        cmd.extend(["-vn", "-c:a", "pcm_s16le"])

    elif target_format == "m4a":
        cmd.extend(["-vn", "-c:a", "aac", "-b:a", "192k"])

    else:
        cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-threads", "2", "-c:a", "aac"])

    if video_filters:
        cmd.extend(["-vf", ",".join(video_filters)])

    cmd.extend(["-progress", "pipe:1", "-nostats", str(output_path)])
    return cmd

def run_conversion_job(task_id):
    """Ejecuta FFmpeg para una tarea y actualiza el progreso en tiempo real."""
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return
        task["status"] = "converting"
        task["progress"] = 0
        task["started_at"] = time.time()
        save_tasks_to_disk()

    input_path = Path(task["input_path"])
    output_path = Path(task["output_path"])
    target_format = task["target_format"]
    options = task.get("options", {})

    duration = get_media_duration(input_path)
    with tasks_lock:
        task["duration"] = duration

    cmd = build_ffmpeg_cmd(input_path, output_path, target_format, options)
    print(f"[FFmpeg] Iniciando conversión {task_id}: {' '.join(cmd)}")

    err_file = UPLOADS_DIR / f"{task_id}.err"
    try:
        with open(err_file, "w", encoding="utf-8") as err_f:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=err_f,
                text=True,
                bufsize=1
            )

            for line in proc.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        time_us = int(line.split("=")[1])
                        elapsed_seconds = time_us / 1_000_000.0
                        if duration and duration > 0:
                            pct = int((elapsed_seconds / duration) * 100)
                            pct = max(0, min(99, pct))
                            with tasks_lock:
                                task["progress"] = pct
                    except Exception:
                        pass
                elif line.startswith("progress=") and line.endswith("end"):
                    with tasks_lock:
                        task["progress"] = 100

            proc.wait()

        stderr_err = ""
        if err_file.exists():
            try:
                stderr_err = err_file.read_text(encoding="utf-8", errors="ignore")
                err_file.unlink(missing_ok=True)
            except Exception:
                pass

        if proc.returncode == 0 and output_path.exists():
            out_size = output_path.stat().st_size
            with tasks_lock:
                task["status"] = "completed"
                task["progress"] = 100
                task["output_size"] = out_size
                task["completed_at"] = time.time()
                elapsed = task["completed_at"] - task["started_at"]
                task["elapsed_seconds"] = round(elapsed, 1)
                save_tasks_to_disk()
            print(f"[FFmpeg] Conversión {task_id} finalizada exitosamente en {round(elapsed, 1)}s. Tamaño: {out_size} bytes.")
        else:
            with tasks_lock:
                task["status"] = "error"
                task["error_message"] = (stderr_err[-300:] if stderr_err else "Error durante la conversión FFmpeg").strip()
                save_tasks_to_disk()
            print(f"[FFmpeg] Error en conversión {task_id}: {stderr_err}")

    except Exception as e:
        with tasks_lock:
            task["status"] = "error"
            task["error_message"] = str(e)
            save_tasks_to_disk()
        print(f"[FFmpeg] Excepción en conversión {task_id}: {e}", file=sys.stderr)


class VideoConverterHandler(BaseHTTPRequestHandler):
    """Manejador HTTP para la interfaz web y APIs REST."""

    def log_message(self, format, *args):
        try:
            # Desactivar logs ruidosos para polling continuo y comprobar tipo seguro
            if args and isinstance(args[0], str) and "GET /api/tasks" in args[0]:
                return
        except Exception:
            pass
        super().log_message(format, *args)

    def do_HEAD(self):
        """Soporte para peticiones HEAD (usadas habitualmente por health checks de Render, Railway, etc.)."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ["/", "/index.html", "/health", "/healthz"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = (STATIC_DIR / rel_path).resolve()
            if str(file_path).startswith(str(STATIC_DIR.resolve())) and file_path.exists():
                ext = file_path.suffix.lower()
                mime = MIME_TYPES.get(ext, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(file_path.stat().st_size))
                self.end_headers()
            else:
                self.send_error(404, "Archivo no encontrado")
        else:
            self.send_response(200)
            self.end_headers()

    def send_json(self, data, status=200):
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/health", "/healthz"]:
            self.send_json({"status": "ok"})
            return

        if path == "/" or path == "/index.html":
            self.serve_file(TEMPLATES_DIR / "index.html", "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            file_path = (STATIC_DIR / rel_path).resolve()
            if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.exists():
                self.send_error(404, "Archivo no encontrado")
                return
            ext = file_path.suffix.lower()
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            self.serve_file(file_path, mime)
        elif path == "/api/tasks":
            with tasks_lock:
                task_list = list(tasks.values())
            self.send_json({"tasks": task_list})
        elif path.startswith("/api/tasks/"):
            task_id = path.split("/api/tasks/")[1]
            with tasks_lock:
                task = tasks.get(task_id)
            if task:
                self.send_json({"task": task})
            else:
                self.send_error(404, "Tarea no encontrada")
        elif path.startswith("/api/download/"):
            task_id = path.split("/api/download/")[1]
            with tasks_lock:
                task = tasks.get(task_id)
            if not task or task.get("status") != "completed":
                self.send_error(404, "Archivo convertido no disponible")
                return
            out_path = Path(task["output_path"])
            if not out_path.exists():
                self.send_error(404, "Archivo físico no encontrado")
                return
            filename = task["output_name"]
            self.serve_download(out_path, filename=filename)
        elif path.startswith("/api/preview/"):
            task_id = path.split("/api/preview/")[1]
            with tasks_lock:
                task = tasks.get(task_id)
            if not task or task.get("status") != "completed":
                self.send_error(404, "Archivo no disponible para previsualizar")
                return
            out_path = Path(task["output_path"])
            ext = out_path.suffix.lower()
            mime = MIME_TYPES.get(ext, "video/mp4")
            self.serve_file(out_path, mime)
        elif path == "/api/download-all":
            self.serve_zip_all()
        else:
            self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/upload":
            self.handle_upload()
        elif path == "/api/clear":
            self.handle_clear_all()
        elif path.startswith("/api/convert/"):
            task_id = path.split("/api/convert/")[1]
            query_params = urllib.parse.parse_qs(parsed.query)
            self.handle_start_convert(task_id, query_params)
        elif path == "/api/convert-all":
            self.handle_convert_all()
        else:
            self.send_error(404, "Acción POST no encontrada")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/tasks/"):
            task_id = path.split("/api/tasks/")[1]
            with tasks_lock:
                task = tasks.pop(task_id, None)
            if task:
                try:
                    if Path(task["input_path"]).exists():
                        os.remove(task["input_path"])
                    if Path(task["output_path"]).exists():
                        os.remove(task["output_path"])
                except Exception:
                    pass
                save_tasks_to_disk()
                self.send_json({"success": True, "task_id": task_id})
            else:
                self.send_error(404, "Tarea no encontrada")
        else:
            self.send_error(404, "Ruta DELETE no encontrada")

    def handle_upload(self):
        """Maneja la subida de un archivo en streaming binario para máxima eficiencia."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_filename = self.headers.get("X-Filename", "video.mpg")
            filename = urllib.parse.unquote(raw_filename)
            target_format = self.headers.get("X-Target-Format", "mp4").lower().strip()
            quality = self.headers.get("X-Quality", "normal")
            resolution = self.headers.get("X-Resolution", "original")
            audio = self.headers.get("X-Audio", "default")
            # Por defecto NO auto-iniciar para permitir al usuario revisar y elegir formato
            auto_start = self.headers.get("X-Auto-Start", "false").lower() == "true"

            # Sanitizar nombre de archivo
            safe_name = os.path.basename(filename).replace("/", "_").replace("\\", "_")
            if not safe_name:
                safe_name = "video.mpg"

            task_id = str(uuid.uuid4())[:8]
            input_file = UPLOADS_DIR / f"{task_id}_{safe_name}"

            stem = Path(safe_name).stem
            output_name = f"{stem}.{target_format}"
            output_file = CONVERTED_DIR / f"{task_id}_{output_name}"

            # Escribir flujo de bytes en bloques de 64 KB
            bytes_left = content_length
            with open(input_file, "wb") as f:
                chunk_size = 64 * 1024
                while bytes_left > 0:
                    read_len = min(chunk_size, bytes_left)
                    chunk = self.rfile.read(read_len)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_left -= len(chunk)

            file_size = input_file.stat().st_size

            task_data = {
                "id": task_id,
                "original_name": safe_name,
                "input_path": str(input_file),
                "output_name": output_name,
                "output_path": str(output_file),
                "target_format": target_format,
                "input_size": file_size,
                "output_size": None,
                "status": "queued",
                "progress": 0,
                "options": {
                    "quality": quality,
                    "resolution": resolution,
                    "audio": audio
                },
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "elapsed_seconds": None,
                "duration": None,
                "error_message": None
            }

            with tasks_lock:
                tasks[task_id] = task_data
            save_tasks_to_disk()

            if auto_start:
                conversion_executor.submit(run_conversion_job, task_id)

            self.send_json({"success": True, "task": task_data})

        except Exception as e:
            print(f"[Upload Error]: {e}", file=sys.stderr)
            self.send_json({"success": False, "error": str(e)}, status=500)

    def handle_start_convert(self, task_id, query_params=None):
        with tasks_lock:
            task = tasks.get(task_id)
            if not task:
                self.send_error(404, "Tarea no encontrada")
                return
            if query_params:
                new_fmt = query_params.get("target", [None])[0]
                if new_fmt:
                    task["target_format"] = new_fmt.lower().strip()
                    stem = Path(task["original_name"]).stem
                    task["output_name"] = f"{stem}.{task['target_format']}"
                    task["output_path"] = str(CONVERTED_DIR / f"{task_id}_{task['output_name']}")

            if task["status"] == "converting":
                self.send_json({"success": True, "message": "Ya en proceso"})
                return
            task["status"] = "queued"
            task["progress"] = 0
            task["error_message"] = None
            save_tasks_to_disk()

        conversion_executor.submit(run_conversion_job, task_id)
        self.send_json({"success": True, "task_id": task_id})

    def handle_convert_all(self):
        queued_ids = []
        with tasks_lock:
            for tid, t in tasks.items():
                if t["status"] in ["queued", "error"]:
                    queued_ids.append(tid)

        for tid in queued_ids:
            conversion_executor.submit(run_conversion_job, tid)

        self.send_json({"success": True, "count": len(queued_ids)})

    def handle_clear_all(self):
        with tasks_lock:
            to_delete = list(tasks.values())
            tasks.clear()

        for t in to_delete:
            try:
                if Path(t["input_path"]).exists():
                    os.remove(t["input_path"])
                if Path(t["output_path"]).exists():
                    os.remove(t["output_path"])
            except Exception:
                pass

        save_tasks_to_disk()
        self.send_json({"success": True, "message": "Historial limpiado"})

    def serve_file(self, file_path, content_type):
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error leyendo archivo: {e}")

    def serve_download(self, file_path, filename):
        try:
            size = file_path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            encoded_fn = urllib.parse.quote(filename)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_fn}')
            self.send_header("Content-Length", str(size))
            self.end_headers()

            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, length=64 * 1024)
        except Exception as e:
            print(f"[Download Error]: {e}", file=sys.stderr)

    def serve_zip_all(self):
        """Genera un archivo ZIP con todos los videos convertidos."""
        with tasks_lock:
            completed_tasks = [t for t in tasks.values() if t["status"] == "completed"]

        if not completed_tasks:
            self.send_error(400, "No hay archivos convertidos listos para descargar")
            return

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for t in completed_tasks:
                out_path = Path(t["output_path"])
                if out_path.exists():
                    zf.write(out_path, arcname=t["output_name"])

        zip_data = zip_buffer.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="videos_convertidos.zip"')
        self.send_header("Content-Length", str(len(zip_data)))
        self.end_headers()
        self.wfile.write(zip_data)


def find_available_port(start_port=8080, max_attempts=20):
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return start_port

def run_server(port=None):
    load_tasks_from_disk()
    if port is None:
        port = find_available_port(8080)
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, VideoConverterHandler)
    print("\n" + "="*60)
    print("🎬  CONVERSOR DE VIDEO MULTI-ARCHIVO WEB CON FFMPEG")
    print("="*60)
    print(f"✅  Servidor activo en: http://localhost:{port}")
    print(f"📁  Directorio de subidas: {UPLOADS_DIR}")
    print(f"📁  Directorio convertidos: {CONVERTED_DIR}")
    print("="*60)
    print("Presiona Ctrl+C para detener el servidor.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor...")
        httpd.server_close()
        print("Servidor detenido correctamente.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        port_arg = int(sys.argv[1])
    elif "PORT" in os.environ:
        port_arg = int(os.environ["PORT"])
    else:
        port_arg = None
    run_server(port_arg)
