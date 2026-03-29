const state = {
  live: {},
  streams: [],
  waterfall: {},
};

const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.panel');
const liveStreamSelect = document.getElementById('live-stream');
const liveCanvas = document.getElementById('live-canvas');
const liveInfo = document.getElementById('live-info');
const liveTs = document.getElementById('live-ts');
const waterfallStreamSelect = document.getElementById('waterfall-stream');
const waterfallCanvas = document.getElementById('waterfall-canvas');
const waterfallInfo = document.getElementById('waterfall-info');
const historyWindow = document.getElementById('history-window');
const historyValue = document.getElementById('history-value');
const viewModeSelect = document.getElementById('view-mode');
const streamList = document.getElementById('stream-list');
const addStreamBtn = document.getElementById('add-stream');
const saveStreamsBtn = document.getElementById('save-streams');
const saveStatus = document.getElementById('save-status');

state.viewMode = localStorage.getItem('audio-spectrum-view-mode') || 'log';
if (viewModeSelect) {
  viewModeSelect.value = state.viewMode;
}

function setActiveTab(name) {
  tabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.tab === name));
  panels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${name}`));
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => setActiveTab(tab.dataset.tab));
});

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

function dbToColor(db) {
  const n = clamp((db + 90) / 90, 0, 1);
  const r = Math.round(20 + n * 220);
  const g = Math.round(20 + Math.sin(n * Math.PI) * 180);
  const b = Math.round(200 - n * 170);
  return `rgb(${r},${g},${b})`;
}

function drawDbLegend(ctx, x, y, w, h, minDb, maxDb) {
  for (let i = 0; i < h; i++) {
    const ratio = 1 - i / h;
    const db = minDb + ratio * (maxDb - minDb);
    ctx.fillStyle = dbToColor(db);
    ctx.fillRect(x, y + i, w, 1);
  }

  ctx.strokeStyle = '#486180';
  ctx.strokeRect(x, y, w, h);

  ctx.fillStyle = '#d8e7fa';
  ctx.font = '11px sans-serif';
  ctx.fillText(`${maxDb} dB`, x + w + 6, y + 10);
  ctx.fillText(`${Math.round((maxDb + minDb) / 2)} dB`, x + w + 6, y + h / 2 + 4);
  ctx.fillText(`${minDb} dB`, x + w + 6, y + h - 2);
}

function slugify(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'stream';
}

function xForFrequency(freqHz, minHz, maxHz, chartW, mode) {
  const safeFreq = Math.max(freqHz, minHz);
  if (mode === 'linear') {
    return ((safeFreq - minHz) / Math.max(1e-9, maxHz - minHz)) * chartW;
  }
  const minL = Math.log10(Math.max(minHz, 1e-9));
  const maxL = Math.log10(Math.max(maxHz, minHz + 1e-9));
  const fL = Math.log10(Math.max(safeFreq, minHz));
  return ((fL - minL) / Math.max(1e-9, maxL - minL)) * chartW;
}

function frequencyForX(x, minHz, maxHz, chartW, mode) {
  const ratio = clamp(x / Math.max(1, chartW), 0, 1);
  if (mode === 'linear') {
    return minHz + ratio * (maxHz - minHz);
  }
  const minL = Math.log10(Math.max(minHz, 1e-9));
  const maxL = Math.log10(Math.max(maxHz, minHz + 1e-9));
  const valueL = minL + ratio * (maxL - minL);
  return Math.pow(10, valueL);
}

function formatHz(freqHz) {
  if (freqHz >= 1000) {
    const k = freqHz / 1000;
    return Number.isInteger(k) ? `${k}k` : `${k.toFixed(1)}k`;
  }
  return `${Math.round(freqHz)}`;
}

function getAxisTicks(minHz, maxHz, mode) {
  const logTicks = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 8000, 10000, 12000, 16000, 20000];
  const linearTicks = [10, 1000, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000, 18000, 20000];
  const source = mode === 'linear' ? linearTicks : logTicks;
  return source.filter((f) => f >= minHz && f <= maxHz);
}

function drawFrequencyAxis(ctx, minHz, maxHz, mode, chartX, chartY, chartW, chartH) {
  const ticks = getAxisTicks(minHz, maxHz, mode);
  ctx.font = '11px sans-serif';

  ticks.forEach((freq) => {
    const x = chartX + xForFrequency(freq, minHz, maxHz, chartW, mode);

    ctx.strokeStyle = '#223249';
    ctx.beginPath();
    ctx.moveTo(x, chartY);
    ctx.lineTo(x, chartY + chartH);
    ctx.stroke();

    ctx.strokeStyle = '#6f89a8';
    ctx.beginPath();
    ctx.moveTo(x, chartY + chartH);
    ctx.lineTo(x, chartY + chartH + 5);
    ctx.stroke();

    ctx.fillStyle = '#9db4cf';
    ctx.fillText(formatHz(freq), x - 12, chartY + chartH + 18);
  });
}

function populateStreamSelectors() {
  const liveEntries = Object.values(state.live);
  const configuredEntries = (state.streams || [])
    .filter((s) => s && s.name && s.enabled !== false)
    .map((s) => {
      const slug = slugify(s.name);
      return {
        slug,
        name: s.name,
        spectrum: state.live[slug]?.spectrum,
        detailed: state.live[slug]?.detailed,
        timestamp: state.live[slug]?.timestamp,
      };
    });

  const uniqueBySlug = new Map();
  liveEntries.forEach((entry) => uniqueBySlug.set(entry.slug, entry));
  configuredEntries.forEach((entry) => {
    if (!uniqueBySlug.has(entry.slug)) {
      uniqueBySlug.set(entry.slug, entry);
    }
  });

  const streamEntries = Array.from(uniqueBySlug.values());
  const currentLive = liveStreamSelect.value;
  const currentWaterfall = waterfallStreamSelect.value;
  liveStreamSelect.innerHTML = '';
  waterfallStreamSelect.innerHTML = '';

  streamEntries.forEach((entry) => {
    const optionA = document.createElement('option');
    optionA.value = entry.slug;
    optionA.textContent = entry.name;
    liveStreamSelect.appendChild(optionA);

    const optionB = document.createElement('option');
    optionB.value = entry.slug;
    optionB.textContent = entry.name;
    waterfallStreamSelect.appendChild(optionB);
  });

  if (currentLive && [...liveStreamSelect.options].some((o) => o.value === currentLive)) {
    liveStreamSelect.value = currentLive;
  }
  if (currentWaterfall && [...waterfallStreamSelect.options].some((o) => o.value === currentWaterfall)) {
    waterfallStreamSelect.value = currentWaterfall;
  }
}

function renderLiveSpectrum() {
  const ctx = liveCanvas.getContext('2d');
  const slug = liveStreamSelect.value;
  const entry = slug ? state.live[slug] : null;

  ctx.clearRect(0, 0, liveCanvas.width, liveCanvas.height);
  ctx.fillStyle = '#09111e';
  ctx.fillRect(0, 0, liveCanvas.width, liveCanvas.height);

  if (!entry || !entry.detailed || !Array.isArray(entry.detailed.values) || !entry.detailed.values.length) {
    liveInfo.textContent = 'No live data yet';
    return;
  }

  const rawValues = entry.detailed.values.map((v) => Number(v));
  const framePeakDb = rawValues.length ? Math.max(...rawValues) : 0;
  const detailValues = rawValues.map((v) => clamp(v - framePeakDb, -90, 0));
  const stepHz = Number(entry.detailed.step_hz || 10);
  const minHz = stepHz;
  const maxHz = Number(entry.detailed.max_hz || (detailValues.length * stepHz));
  const viewMode = state.viewMode === 'linear' ? 'linear' : 'log';
  const width = liveCanvas.width;
  const height = liveCanvas.height;
  const marginLeft = 52;
  const marginRight = 74;
  const marginTop = 24;
  const marginBottom = 32;
  const chartW = width - marginLeft - marginRight;
  const chartH = height - marginTop - marginBottom;
  const minDb = -90;
  const maxDb = 0;

  drawFrequencyAxis(ctx, minHz, maxHz, viewMode, marginLeft, marginTop, chartW, chartH);

  ctx.strokeStyle = '#30425e';
  ctx.lineWidth = 1;
  for (let g = 0; g <= 9; g++) {
    const y = marginTop + (chartH / 9) * g;
    ctx.beginPath();
    ctx.moveTo(marginLeft, y);
    ctx.lineTo(width - marginRight, y);
    ctx.stroke();

    const dbLabel = Math.round(maxDb - ((maxDb - minDb) / 9) * g);
    ctx.fillStyle = '#88a3c1';
    ctx.font = '10px sans-serif';
    ctx.fillText(`${dbLabel}`, 18, y + 3);
  }

  ctx.beginPath();
  detailValues.forEach((db, i) => {
    const freq = (i + 1) * stepHz;
    const x = marginLeft + xForFrequency(freq, minHz, maxHz, chartW, viewMode);
    const n = clamp((Number(db) - minDb) / (maxDb - minDb), 0, 1);
    const y = marginTop + (1 - n) * chartH;
    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.lineWidth = 1.4;
  ctx.strokeStyle = '#5ed3ff';
  ctx.stroke();

  const strongest = rawValues.reduce((acc, db, i) => {
    const val = Number(db);
    if (!acc || val > acc.db) {
      return { db: val, idx: i, freq: (i + 1) * stepHz };
    }
    return acc;
  }, null);

  if (strongest) {
    const strongestHz = (strongest.idx + 1) * stepHz;
    const px = marginLeft + xForFrequency(strongestHz, minHz, maxHz, chartW, viewMode);
    const py = marginTop + (1 - clamp((strongest.db - minDb) / (maxDb - minDb), 0, 1)) * chartH;
    ctx.fillStyle = '#ffd166';
    ctx.beginPath();
    ctx.arc(px, py, 3.2, 0, Math.PI * 2);
    ctx.fill();
    liveInfo.textContent = `Peak: ${strongest.db.toFixed(1)} dB at ${strongest.freq} Hz | display normalized to frame peak (10 Hz, ${viewMode})`;
  } else {
    liveInfo.textContent = 'No peaks detected';
  }

  ctx.fillStyle = '#d8e7fa';
  ctx.font = '12px sans-serif';
  ctx.fillText(`scale: ${viewMode}`, marginLeft, height - 10);
  ctx.fillText(`max: ${maxHz} Hz`, width - marginRight - 64, height - 10);

  drawDbLegend(ctx, width - marginRight + 18, marginTop, 14, chartH, minDb, maxDb);

  if (entry.timestamp) {
    const d = new Date(entry.timestamp * 1000);
    liveTs.textContent = `updated ${d.toLocaleTimeString()}`;
  }
}

function renderWaterfall() {
  const ctx = waterfallCanvas.getContext('2d');
  const slug = waterfallStreamSelect.value;
  const streamPayload = (slug && state.waterfall[slug]) ? state.waterfall[slug] : null;
  const frames = streamPayload && Array.isArray(streamPayload.frames) ? streamPayload.frames : [];
  const frameLimit = Number(historyWindow.value);
  const selectedFrames = frames.slice(-frameLimit);

  ctx.clearRect(0, 0, waterfallCanvas.width, waterfallCanvas.height);
  ctx.fillStyle = '#081018';
  ctx.fillRect(0, 0, waterfallCanvas.width, waterfallCanvas.height);

  if (selectedFrames.length === 0) {
    waterfallInfo.textContent = 'No waterfall history yet';
    return;
  }

  const stepHz = Number(streamPayload.step_hz || 10);
  const minHz = stepHz;
  const maxHz = Number(streamPayload.max_hz || 20000);
  const viewMode = state.viewMode === 'linear' ? 'linear' : 'log';
  const binCount = selectedFrames[0]?.values?.length || 0;
  if (!binCount) {
    waterfallInfo.textContent = 'No detailed bins in waterfall data';
    return;
  }

  const minDb = -90;
  const maxDb = 0;
  const marginLeft = 52;
  const marginRight = 74;
  const marginTop = 16;
  const marginBottom = 28;
  const chartW = waterfallCanvas.width - marginLeft - marginRight;
  const chartH = waterfallCanvas.height - marginTop - marginBottom;

  let globalPeakDb = -9999;
  selectedFrames.forEach((frame) => {
    const bins = frame.values || [];
    bins.forEach((v) => {
      const n = Number(v);
      if (n > globalPeakDb) {
        globalPeakDb = n;
      }
    });
  });

  drawFrequencyAxis(ctx, minHz, maxHz, viewMode, marginLeft, marginTop, chartW, chartH);

  selectedFrames.forEach((frame, row) => {
    const bins = frame.values || [];
    const y = marginTop + (row / Math.max(1, selectedFrames.length)) * chartH;
    const nextY = marginTop + ((row + 1) / Math.max(1, selectedFrames.length)) * chartH;
    const h = Math.max(1, Math.ceil(nextY - y));

    for (let x = 0; x < chartW; x++) {
      const freq = frequencyForX(x, minHz, maxHz, chartW - 1, viewMode);
      const idx = clamp(Math.floor(freq / stepHz) - 1, 0, binCount - 1);
      const dbRaw = Number(bins[idx] ?? minDb);
      const db = clamp(dbRaw - globalPeakDb, -90, 0);
      ctx.fillStyle = dbToColor(db);
      ctx.fillRect(marginLeft + x, y, 1, h);
    }
  });

  ctx.fillStyle = '#d8e7fa';
  ctx.font = '12px sans-serif';
  ctx.fillText(`scale: ${viewMode}`, marginLeft, waterfallCanvas.height - 10);
  ctx.fillText(`max: ${maxHz} Hz`, waterfallCanvas.width - marginRight - 64, waterfallCanvas.height - 10);
  ctx.fillText('Past', 8, marginTop + 12);
  ctx.fillText('Now', 10, marginTop + chartH - 2);

  drawDbLegend(ctx, waterfallCanvas.width - marginRight + 18, marginTop, 14, chartH, minDb, maxDb);

  const firstTs = new Date(selectedFrames[0].ts * 1000).toLocaleTimeString();
  const lastTs = new Date(selectedFrames[selectedFrames.length - 1].ts * 1000).toLocaleTimeString();
  waterfallInfo.textContent = `Frames: ${selectedFrames.length} | ${firstTs} -> ${lastTs} | resolution: ${stepHz} Hz | ${viewMode} | normalized to ${globalPeakDb.toFixed(1)} dB peak`;
}

function streamRowTemplate(stream = { name: '', url: '', enabled: true }) {
  const row = document.createElement('div');
  row.className = 'stream-item';
  row.innerHTML = `
    <div class="stream-grid">
      <input type="text" placeholder="Name" value="${stream.name || ''}" class="stream-name">
      <input type="url" placeholder="rtsp://... or rtmp://..." value="${stream.url || ''}" class="stream-url">
      <label><input type="checkbox" class="stream-enabled" ${stream.enabled ? 'checked' : ''}> Enabled</label>
      <button class="danger remove-stream">Remove</button>
    </div>
  `;
  row.querySelector('.remove-stream').addEventListener('click', () => row.remove());
  return row;
}

function renderSettings() {
  streamList.innerHTML = '';
  const streams = state.streams.length ? state.streams : [{ name: '', url: '', enabled: true }];
  streams.forEach((s) => streamList.appendChild(streamRowTemplate(s)));
}

function collectStreamsFromUi() {
  const rows = streamList.querySelectorAll('.stream-item');
  const streams = [];
  rows.forEach((row) => {
    const name = row.querySelector('.stream-name').value.trim();
    const url = row.querySelector('.stream-url').value.trim();
    const enabled = row.querySelector('.stream-enabled').checked;
    if (name && url) streams.push({ name, url, enabled });
  });
  return streams;
}

async function refreshLive() {
  const resp = await fetch('./api/live', { cache: 'no-store' });
  const payload = await resp.json();
  state.live = payload.live || {};
  if (Array.isArray(payload.streams)) {
    state.streams = payload.streams;
  }
  populateStreamSelectors();
  renderLiveSpectrum();
}

async function refreshWaterfall() {
  const resp = await fetch('./api/waterfall', { cache: 'no-store' });
  state.waterfall = await resp.json();
  renderWaterfall();
}

async function refreshConfig() {
  const resp = await fetch('./api/config', { cache: 'no-store' });
  const payload = await resp.json();
  state.streams = payload.streams || [];
  renderSettings();
  populateStreamSelectors();
}

historyWindow.addEventListener('input', () => {
  historyValue.textContent = historyWindow.value;
  renderWaterfall();
});

liveStreamSelect.addEventListener('change', renderLiveSpectrum);
waterfallStreamSelect.addEventListener('change', renderWaterfall);

if (viewModeSelect) {
  viewModeSelect.addEventListener('change', () => {
    state.viewMode = viewModeSelect.value === 'linear' ? 'linear' : 'log';
    localStorage.setItem('audio-spectrum-view-mode', state.viewMode);
    renderLiveSpectrum();
    renderWaterfall();
  });
}

addStreamBtn.addEventListener('click', () => {
  streamList.appendChild(streamRowTemplate());
});

saveStreamsBtn.addEventListener('click', async () => {
  const streams = collectStreamsFromUi();
  saveStatus.textContent = 'Saving...';
  const resp = await fetch('./api/config/streams', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ streams }),
  });

  if (!resp.ok) {
    saveStatus.textContent = 'Save failed';
    return;
  }

  const payload = await resp.json();
  state.streams = payload.streams || streams;
  saveStatus.textContent = 'Saved. Stream workers reconfigured.';
  await refreshConfig();
  await refreshLive();
  await refreshWaterfall();
});

async function boot() {
  await Promise.all([refreshConfig(), refreshLive(), refreshWaterfall()]);
  setInterval(refreshLive, 700);
  setInterval(refreshWaterfall, 1200);
}

boot().catch((err) => {
  console.error(err);
  saveStatus.textContent = 'Failed to load UI data';
});
