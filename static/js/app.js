/**
 * Conversor Universal de Video - Frontend Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elementos DOM
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const globalControls = document.getElementById('globalControls');
  const queueHeader = document.getElementById('queueHeader');
  const videoList = document.getElementById('videoList');
  const emptyState = document.getElementById('emptyState');
  const summaryCount = document.getElementById('summaryCount');
  const summaryTotalSize = document.getElementById('summaryTotalSize');
  const globalFormat = document.getElementById('globalFormat');
  const globalQuality = document.getElementById('globalQuality');
  const globalResolution = document.getElementById('globalResolution');
  const globalAudio = document.getElementById('globalAudio');
  const toggleAdvancedBtn = document.getElementById('toggleAdvancedBtn');
  const advancedPanel = document.getElementById('advancedPanel');
  const startAllBtn = document.getElementById('startAllBtn');
  const downloadZipBtn = document.getElementById('downloadZipBtn');
  const clearAllBtn = document.getElementById('clearAllBtn');
  const previewModal = document.getElementById('previewModal');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const previewVideoPlayer = document.getElementById('previewVideoPlayer');
  const modalTitle = document.getElementById('modalTitle');

  // Estado local
  let tasks = {}; // task_id -> task object
  let pollInterval = null;
  let isAdvancedOpen = false;

  // Formatos soportados para selector
  const availableFormats = [
    { value: 'mp4', label: 'MP4 (Universal)' },
    { value: 'mkv', label: 'MKV' },
    { value: 'webm', label: 'WEBM' },
    { value: 'mov', label: 'MOV' },
    { value: 'avi', label: 'AVI' },
    { value: 'mpg', label: 'MPG' },
    { value: 'gif', label: 'GIF' },
    { value: 'mp3', label: 'MP3 (Audio)' },
    { value: 'wav', label: 'WAV (Audio)' },
    { value: 'm4a', label: 'M4A (Audio)' },
  ];

  // Helper para formatear bytes
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  // Helper para obtener extensión de archivo
  function getExtension(filename) {
    if (!filename) return 'VID';
    const parts = filename.split('.');
    return parts.length > 1 ? parts.pop().toUpperCase() : 'VID';
  }

  // Configuración de Drag & Drop
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('click', () => {
    fileInput.click();
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      handleFiles(Array.from(files));
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(Array.from(e.target.files));
      fileInput.value = ''; // Limpiar para permitir re-selección
    }
  });

  // Alternar ajustes avanzados
  toggleAdvancedBtn.addEventListener('click', () => {
    isAdvancedOpen = !isAdvancedOpen;
    advancedPanel.style.display = isAdvancedOpen ? 'block' : 'none';
    toggleAdvancedBtn.classList.toggle('active', isAdvancedOpen);
  });

  // Cambio de formato global: actualiza las tareas pendientes
  globalFormat.addEventListener('change', () => {
    const newTarget = globalFormat.value;
    Object.values(tasks).forEach(task => {
      if (task.status === 'queued') {
        task.target_format = newTarget;
        const select = document.getElementById(`target-select-${task.id}`);
        if (select) select.value = newTarget;
      }
    });
  });

  // Iniciar todas las conversiones pendientes
  startAllBtn.addEventListener('click', async () => {
    try {
      startAllBtn.disabled = true;
      const res = await fetch('/api/convert-all', { method: 'POST' });
      if (res.ok) {
        startPolling();
      }
    } catch (err) {
      console.error('Error al iniciar conversiones:', err);
    } finally {
      startAllBtn.disabled = false;
    }
  });

  // Descargar todo en ZIP
  downloadZipBtn.addEventListener('click', () => {
    window.location.href = '/api/download-all';
  });

  // Limpiar lista
  clearAllBtn.addEventListener('click', async () => {
    if (!confirm('¿Deseas limpiar todos los archivos de la lista?')) return;
    try {
      await fetch('/api/clear', { method: 'POST' });
      tasks = {};
      stopPolling();
      renderUI();
    } catch (err) {
      console.error('Error limpiando:', err);
    }
  });

  // Procesar y subir múltiples archivos
  function handleFiles(files) {
    files.forEach(file => {
      uploadFile(file);
    });
  }

  // Subida de un archivo en streaming con XMLHttpRequest
  function uploadFile(file) {
    const tempId = 'temp-' + Math.random().toString(36).substring(2, 9);
    const targetFmt = globalFormat.value;
    const quality = globalQuality.value;
    const resolution = globalResolution.value;
    const audio = globalAudio.value;

    // Crear tarea temporal local mientras sube
    tasks[tempId] = {
      id: tempId,
      original_name: file.name,
      target_format: targetFmt,
      input_size: file.size,
      status: 'uploading',
      upload_progress: 0,
      progress: 0
    };

    renderUI();

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload', true);

    // Encabezados con metadatos
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.setRequestHeader('X-Target-Format', targetFmt);
    xhr.setRequestHeader('X-Quality', quality);
    xhr.setRequestHeader('X-Resolution', resolution);
    xhr.setRequestHeader('X-Audio', audio);
    xhr.setRequestHeader('X-Auto-Start', 'true');

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        if (tasks[tempId]) {
          tasks[tempId].upload_progress = pct;
          updateCardProgress(tempId, pct, 'Subiendo...');
        }
      }
    };

    xhr.onload = () => {
      if (xhr.status === 200) {
        try {
          const resp = JSON.parse(xhr.responseText);
          if (resp.success && resp.task) {
            delete tasks[tempId];
            tasks[resp.task.id] = resp.task;
            renderUI();
            startPolling();
          }
        } catch (e) {
          console.error('Error parseando respuesta:', e);
        }
      } else {
        if (tasks[tempId]) {
          tasks[tempId].status = 'error';
          tasks[tempId].error_message = 'Fallo al subir el archivo al servidor';
          renderUI();
        }
      }
    };

    xhr.onerror = () => {
      if (tasks[tempId]) {
        tasks[tempId].status = 'error';
        tasks[tempId].error_message = 'Error de red durante la subida';
        renderUI();
      }
    };

    xhr.send(file);
  }

  // Polling continuo del estado de las tareas
  function startPolling() {
    if (pollInterval) return;
    pollTasks();
    pollInterval = setInterval(pollTasks, 800);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  async function pollTasks() {
    try {
      const res = await fetch('/api/tasks');
      if (!res.ok) return;
      const data = await res.json();
      
      let hasActiveJobs = false;
      const updatedTasks = {};

      data.tasks.forEach(t => {
        updatedTasks[t.id] = t;
        if (t.status === 'converting' || t.status === 'queued') {
          hasActiveJobs = true;
        }
      });

      // Conservar las que aún estén en estado 'uploading' local
      Object.keys(tasks).forEach(id => {
        if (tasks[id].status === 'uploading') {
          updatedTasks[id] = tasks[id];
          hasActiveJobs = true;
        }
      });

      tasks = updatedTasks;
      renderUI();

      if (!hasActiveJobs) {
        stopPolling();
      }
    } catch (err) {
      console.warn('Error en sondeo de tareas:', err);
    }
  }

  // Renderizar o actualizar la interfaz
  function renderUI() {
    const taskIds = Object.keys(tasks);
    const hasTasks = taskIds.length > 0;

    emptyState.style.display = hasTasks ? 'none' : 'block';
    globalControls.style.display = hasTasks ? 'block' : 'none';
    queueHeader.style.display = hasTasks ? 'flex' : 'none';

    if (!hasTasks) {
      videoList.innerHTML = '';
      return;
    }

    // Calcular estadísticas globales
    let totalSize = 0;
    let completedCount = 0;
    taskIds.forEach(id => {
      const t = tasks[id];
      totalSize += t.input_size || 0;
      if (t.status === 'completed') completedCount++;
    });

    summaryCount.textContent = `${taskIds.length} video${taskIds.length === 1 ? '' : 's'}`;
    summaryTotalSize.textContent = `(${formatBytes(totalSize)})`;
    downloadZipBtn.disabled = completedCount === 0;

    // Actualizar o crear tarjetas
    const existingCards = new Set();
    videoList.querySelectorAll('.video-card').forEach(el => {
      existingCards.add(el.dataset.taskId);
    });

    taskIds.forEach(id => {
      const task = tasks[id];
      if (existingCards.has(id)) {
        updateCardDOM(id, task);
      } else {
        createCardDOM(task);
      }
    });

    // Eliminar tarjetas que ya no existen en tasks
    existingCards.forEach(id => {
      if (!tasks[id]) {
        const card = document.querySelector(`.video-card[data-task-id="${id}"]`);
        if (card) card.remove();
      }
    });
  }

  // Crear elemento DOM de la tarjeta
  function createCardDOM(task) {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.dataset.taskId = task.id;

    const ext = getExtension(task.original_name);

    card.innerHTML = `
      <div class="video-card-main">
        <div class="video-file-info">
          <span class="format-badge">${ext}</span>
          <div class="file-details">
            <span class="file-name" title="${task.original_name}">${task.original_name}</span>
            <div class="file-meta">
              <span class="original-size">${formatBytes(task.input_size)}</span>
              <span class="status-indicator"></span>
            </div>
          </div>
        </div>

        <div class="conversion-config-bar">
          <span class="arrow-icon">&rarr;</span>
          <select class="select-custom card-target-select" id="target-select-${task.id}">
            ${availableFormats.map(f => `<option value="${f.value}" ${task.target_format === f.value ? 'selected' : ''}>${f.label}</option>`).join('')}
          </select>
        </div>

        <div class="card-actions" id="actions-${task.id}">
          <!-- Botones contextuales según estado -->
        </div>
      </div>

      <div class="progress-container" id="progress-container-${task.id}">
        <div class="progress-header">
          <span class="progress-status-text" id="status-text-${task.id}">Preparando...</span>
          <span class="progress-percentage" id="pct-text-${task.id}">0%</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" id="progress-fill-${task.id}"></div>
        </div>
      </div>

      <div class="card-error-msg" id="error-msg-${task.id}" style="display: none;"></div>
    `;

    // Selector individual de formato
    const select = card.querySelector(`#target-select-${task.id}`);
    select.addEventListener('change', (e) => {
      task.target_format = e.target.value;
    });

    videoList.appendChild(card);
    updateCardDOM(task.id, task);
  }

  // Actualizar estado de una tarjeta existente
  function updateCardDOM(taskId, task) {
    const card = document.querySelector(`.video-card[data-task-id="${taskId}"]`);
    if (!card) return;

    const select = card.querySelector(`#target-select-${taskId}`);
    const statusText = card.querySelector(`#status-text-${taskId}`);
    const pctText = card.querySelector(`#pct-text-${taskId}`);
    const progressFill = card.querySelector(`#progress-fill-${taskId}`);
    const actionsBox = card.querySelector(`#actions-${taskId}`);
    const errorBox = card.querySelector(`#error-msg-${taskId}`);
    const statusIndicator = card.querySelector('.status-indicator');

    // Deshabilitar selector si ya empezó a convertir o terminó
    if (select) {
      select.disabled = task.status !== 'queued';
    }

    // Limpiar clases previas de fill
    progressFill.className = 'progress-fill';

    if (task.status === 'uploading') {
      const pct = task.upload_progress || 0;
      statusText.innerHTML = `<span>Subiendo archivo...</span>`;
      pctText.textContent = `${pct}%`;
      progressFill.style.width = `${pct}%`;
      statusIndicator.innerHTML = `<span class="status-badge status-uploading">Subiendo</span>`;
      actionsBox.innerHTML = '';
      errorBox.style.display = 'none';

    } else if (task.status === 'queued') {
      statusText.innerHTML = `<span>En cola de conversión</span>`;
      pctText.textContent = `Listo`;
      progressFill.style.width = `0%`;
      statusIndicator.innerHTML = `<span class="status-badge status-queued">En espera</span>`;
      actionsBox.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="startSingleConvert('${task.id}')">
          Convertir
        </button>
        <button class="btn btn-ghost btn-sm" onclick="deleteTask('${task.id}')" title="Eliminar">
          &times;
        </button>
      `;
      errorBox.style.display = 'none';

    } else if (task.status === 'converting') {
      const pct = task.progress || 0;
      progressFill.classList.add('converting');
      progressFill.style.width = `${Math.max(5, pct)}%`;
      statusText.innerHTML = `<span class="pulse-dot"></span> Procesando con FFmpeg...`;
      pctText.textContent = `${pct}%`;
      statusIndicator.innerHTML = `<span class="status-badge status-converting">Codificando</span>`;
      actionsBox.innerHTML = `
        <button class="btn btn-ghost btn-sm" disabled>
          Procesando...
        </button>
      `;
      errorBox.style.display = 'none';

    } else if (task.status === 'completed') {
      progressFill.classList.add('completed');
      progressFill.style.width = '100%';

      const outSizeStr = formatBytes(task.output_size);
      const elapsedStr = task.elapsed_seconds ? ` en ${task.elapsed_seconds}s` : '';

      // Comparación de tamaño
      let diffHtml = '';
      if (task.input_size && task.output_size) {
        const diffPct = Math.round(((task.output_size - task.input_size) / task.input_size) * 100);
        const diffColor = diffPct < 0 ? '#10b981' : '#f59e0b';
        const sign = diffPct > 0 ? '+' : '';
        diffHtml = ` <small style="color:${diffColor}; font-weight:700;">(${sign}${diffPct}%)</small>`;
      }

      statusText.innerHTML = `✅ ¡Conversión completada${elapsedStr}!`;
      pctText.innerHTML = `<strong>${outSizeStr}</strong>${diffHtml}`;
      statusIndicator.innerHTML = `<span class="status-badge status-completed">Completado</span>`;

      // Comprobar si es previsualizable (MP4, WEBM)
      const canPreview = ['mp4', 'webm'].includes(task.target_format.toLowerCase());

      actionsBox.innerHTML = `
        ${canPreview ? `
          <button class="btn btn-ghost btn-sm" onclick="openPreview('${task.id}', '${task.output_name}')">
            ▶ Ver
          </button>
        ` : ''}
        <a class="btn btn-success btn-sm" href="/api/download/${task.id}" download="${task.output_name}">
          Descargar
        </a>
        <button class="btn btn-ghost btn-sm" onclick="deleteTask('${task.id}')" title="Eliminar">
          &times;
        </button>
      `;
      errorBox.style.display = 'none';

    } else if (task.status === 'error') {
      progressFill.classList.add('error');
      progressFill.style.width = '100%';
      statusText.textContent = `❌ Falló la conversión`;
      pctText.textContent = `Error`;
      statusIndicator.innerHTML = `<span class="status-badge status-error">Error</span>`;
      actionsBox.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="startSingleConvert('${task.id}')">
          Reintentar
        </button>
        <button class="btn btn-ghost btn-sm" onclick="deleteTask('${task.id}')" title="Eliminar">
          &times;
        </button>
      `;
      if (task.error_message) {
        errorBox.textContent = task.error_message;
        errorBox.style.display = 'block';
      }
    }
  }

  // Progreso visual fluido durante la subida
  function updateCardProgress(taskId, pct, label) {
    const card = document.querySelector(`.video-card[data-task-id="${taskId}"]`);
    if (!card) return;
    const progressFill = card.querySelector(`#progress-fill-${taskId}`);
    const pctText = card.querySelector(`#pct-text-${taskId}`);
    const statusText = card.querySelector(`#status-text-${taskId}`);

    if (progressFill) progressFill.style.width = `${pct}%`;
    if (pctText) pctText.textContent = `${pct}%`;
    if (statusText) statusText.textContent = label;
  }

  // Funciones globales expuestas al DOM (para los botones onclick)
  window.startSingleConvert = async (taskId) => {
    try {
      await fetch(`/api/convert/${taskId}`, { method: 'POST' });
      startPolling();
    } catch (err) {
      console.error('Error al convertir tarea individual:', err);
    }
  };

  window.deleteTask = async (taskId) => {
    try {
      await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
      delete tasks[taskId];
      renderUI();
    } catch (err) {
      console.error('Error eliminando tarea:', err);
    }
  };

  window.openPreview = (taskId, filename) => {
    modalTitle.textContent = `Previsualización: ${filename}`;
    previewVideoPlayer.src = `/api/preview/${taskId}`;
    previewModal.style.display = 'flex';
    previewVideoPlayer.play().catch(() => {});
  };

  closeModalBtn.addEventListener('click', () => {
    previewVideoPlayer.pause();
    previewVideoPlayer.src = '';
    previewModal.style.display = 'none';
  });

  previewModal.addEventListener('click', (e) => {
    if (e.target === previewModal) {
      closeModalBtn.click();
    }
  });

  // Cargar tareas existentes al cargar la página
  pollTasks();
});
