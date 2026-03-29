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
const streamList = document.getElementById('stream-list');
const addStreamBtn = document.getElementById('add-stream');
const saveStreamsBtn = document.getElementById('save-streams');
const saveStatus = document.getElementById('save-status');

function setActiveTab(name) {
  tabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.tab === name));
  panels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${name}`));
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => setActiveTab(tab.dataset.tab));
});

function hzKeys() {
  return Array.from({ length: 40 }, (_, i) => String((i + 1) * 500));
}

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

function slugify(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'stream';
}

function populateStreamSelectors() {
  const liveEntries = Object.values(state.live);
  const configuredEntries = (state.streams || [])
    .filter((s) => s && s.name && s.enabled !== false)
    .map((s) => ({
      slug: slugify(s.name),
      name: s.name,
      spectrum: state.live[slugify(s.name)]?.spectrum,
      timestamp: state.live[slugify(s.name)]?.timestamp,
    }));

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

  if (!entry || !entry.spectrum) {
    liveInfo.textContent = 'No live data yet';
    return;
  }

  const keys = hzKeys();
  const bars = keys.map((k) => entry.spectrum[k] || { db: -90, peak_freq_hz: 0 });
  const width = liveCanvas.width;
  const height = liveCanvas.height;
  const margin = 40;
  const chartW = width - margin * 2;
  const chartH = height - margin * 2;
  const barW = chartW / bars.length;

  ctx.strokeStyle = '#30425e';
  ctx.lineWidth = 1;
  for (let g = 0; g <= 9; g++) {
    const y = margin + (chartH / 9) * g;
    ctx.beginPath();
    ctx.moveTo(margin, y);
    ctx.lineTo(width - margin, y);
    ctx.stroke();
  }

  bars.forEach((point, i) => {
    const db = Number(point.db ?? -90);
    const norm = clamp((db + 90) / 90, 0, 1);
    const h = norm * chartH;
    const x = margin + i * barW;
    const y = margin + chartH - h;
    ctx.fillStyle = dbToColor(db);
    ctx.fillRect(x + 1, y, Math.max(1, barW - 2), h);
  });

  ctx.fillStyle = '#d8e7fa';
  ctx.font = '12px sans-serif';
  ctx.fillText('500 Hz', margin, height - 12);
  ctx.fillText('20 kHz', width - margin - 36, height - 12);

  const strongest = bars.reduce((acc, point, i) => {
    const db = Number(point.db ?? -90);
    if (!acc || db > acc.db) return { db, index: i, freq: point.peak_freq_hz };
    return acc;
  }, null);

  liveInfo.textContent = strongest
    ? `Strongest: ${strongest.db.toFixed(1)} dB at ${strongest.freq} Hz`
    : 'No peaks detected';

  if (entry.timestamp) {
    const d = new Date(entry.timestamp * 1000);
    liveTs.textContent = `updated ${d.toLocaleTimeString()}`;
  }
}

function renderWaterfall() {
  const ctx = waterfallCanvas.getContext('2d');
  const slug = waterfallStreamSelect.value;
  const frames = (slug && state.waterfall[slug]) ? state.waterfall[slug] : [];
  const frameLimit = Number(historyWindow.value);
  const selectedFrames = frames.slice(-frameLimit);

  ctx.clearRect(0, 0, waterfallCanvas.width, waterfallCanvas.height);
  ctx.fillStyle = '#081018';
  ctx.fillRect(0, 0, waterfallCanvas.width, waterfallCanvas.height);

  if (selectedFrames.length === 0) {
    waterfallInfo.textContent = 'No waterfall history yet';
    return;
  }

  const keys = hzKeys();
  const cols = keys.length;
  const rows = selectedFrames.length;
  const cellW = waterfallCanvas.width / cols;
  const cellH = waterfallCanvas.height / rows;

  selectedFrames.forEach((frame, row) => {
    const values = frame.values || {};
    keys.forEach((key, col) => {
      const db = Number(values[key]?.db ?? -90);
      ctx.fillStyle = dbToColor(db);
      ctx.fillRect(col * cellW, row * cellH, Math.ceil(cellW), Math.ceil(cellH));
    });
  });

  const firstTs = new Date(selectedFrames[0].ts * 1000).toLocaleTimeString();
  const lastTs = new Date(selectedFrames[selectedFrames.length - 1].ts * 1000).toLocaleTimeString();
  waterfallInfo.textContent = `Frames: ${selectedFrames.length} | ${firstTs} -> ${lastTs}`;
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
  if (Array.isArray(payload.streams) && payload.streams.length) {
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
  setInterval(refreshLive, 1000);
  setInterval(refreshWaterfall, 2000);
}

boot().catch((err) => {
  console.error(err);
  saveStatus.textContent = 'Failed to load UI data';
});
