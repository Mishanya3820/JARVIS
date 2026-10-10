"use strict";

/* ============================================================
 * Constants (mirrors jarvis_gui.py exactly, so a given state
 * always looks the same as it did in the old customtkinter GUI)
 * ============================================================ */
const ACCENT = "#4aa8ff";
const GOOD = "#62d391";
const WARN = "#e5b85c";
const BAD = "#ef7373";

const STATE_COLORS = {
  idle:      { fg: ACCENT, bg: "#12212f" },
  listening: { fg: ACCENT, bg: "#12212f" },
  thinking:  { fg: WARN,   bg: "#2a2417" },
  speaking:  { fg: GOOD,   bg: "#12261c" },
  error:     { fg: BAD,    bg: "#2b171b" },
};
const STATE_LABELS = {
  idle: "READY", listening: "СЛУШАЮ", thinking: "ДУМАЮ",
  speaking: "ГОВОРЮ", error: "ERROR",
};

const RINGS = [58, 49, 38];
const ANGLES = [0, 45, 90, 135, 180, 225, 270, 315];
const BAR_COUNT = 28;
const BAR_BASE_R = 44;
const BAR_MAX_EXTRA = 34;
const LOG_MAX_ENTRIES = 300;

/* ============================================================
 * Global runtime state
 * ============================================================ */
const S = {
  page: "system",
  visualState: "idle",
  animStep: 0,
  micLevelRaw: 0,
  ttsLevel: 0,
  smoothedLevel: 0,
  modelsReady: false,
};

/* ============================================================ Orb ==== */
const orb = document.getElementById("orb");
const ctx = orb.getContext("2d");
const CX = 71, CY = 71;

function drawBase() {
  ctx.beginPath();
  ctx.arc(CX, CY, 43, 0, Math.PI * 2);
  ctx.fillStyle = "#162f49";
  ctx.fill();
  ctx.fillStyle = ACCENT;
  ctx.font = "bold 38px " + getComputedStyle(document.body).fontFamily;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("J", CX, CY + 2);
}

function drawIdleOrError(mode) {
  const isErr = mode === "error";
  const outerC = isErr ? BAD : "#2b5d85";
  const innerC = isErr ? BAD : "#203b55";
  const spokeC = isErr ? BAD : ACCENT;
  const pulse = 1.0 + 0.04 * ((S.animStep % 30) / 30.0);

  RINGS.forEach((radius, i) => {
    const r = radius * pulse;
    ctx.beginPath();
    ctx.arc(CX, CY, r, 0, Math.PI * 2);
    ctx.strokeStyle = i === 0 ? outerC : innerC;
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  const spin = S.animStep * (isErr ? 0.3 : 1.5);
  ANGLES.forEach((angle) => {
    const rad = ((angle + spin) * Math.PI) / 180;
    const x1 = CX + 53 * Math.cos(rad), y1 = CY + 53 * Math.sin(rad);
    const x2 = CX + 58 * Math.cos(rad), y2 = CY + 58 * Math.sin(rad);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = spokeC;
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}

function drawListeningOrSpeaking(mode) {
  const color = mode === "listening" ? ACCENT : GOOD;
  const target = mode === "listening"
    ? Math.min(1.0, S.micLevelRaw * 9.0)
    : S.ttsLevel;
  S.smoothedLevel += (target - S.smoothedLevel) * 0.35;

  for (let i = 0; i < BAR_COUNT; i++) {
    const angle = (360 / BAR_COUNT) * i;
    const wobble = 0.5 + 0.5 * Math.sin(S.animStep * 0.2 + i * 0.8);
    const extra = BAR_MAX_EXTRA * S.smoothedLevel * (0.4 + 0.6 * wobble);
    const r1 = BAR_BASE_R, r2 = BAR_BASE_R + 4 + extra;
    const rad = (angle * Math.PI) / 180;
    const x1 = CX + r1 * Math.cos(rad), y1 = CY + r1 * Math.sin(rad);
    const x2 = CX + r2 * Math.cos(rad), y2 = CY + r2 * Math.sin(rad);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.stroke();
  }
}

function drawThinking() {
  const start = ((S.animStep * 6) % 360) * (Math.PI / 180);
  const extent = (100 * Math.PI) / 180;
  ctx.beginPath();
  ctx.arc(CX, CY, 55, start, start + extent);
  ctx.strokeStyle = WARN;
  ctx.lineWidth = 4;
  ctx.stroke();
}

function renderOrb() {
  ctx.clearRect(0, 0, 142, 142);
  drawBase();
  const mode = S.visualState;
  if (mode === "idle" || mode === "error") drawIdleOrError(mode);
  else if (mode === "listening" || mode === "speaking") drawListeningOrSpeaking(mode);
  else if (mode === "thinking") drawThinking();
  else S.smoothedLevel = 0;
}

function animTick() {
  S.animStep = (S.animStep + 1) % 3600;
  renderOrb();
}
setInterval(animTick, 90);

/* ============================================================
 * Hero pill / status text
 * ============================================================ */
const heroStatus = document.getElementById("heroStatus");
const statusText = document.getElementById("statusText");

window.jarvisSetState = function (state, label) {
  S.visualState = state;
  const colors = STATE_COLORS[state] || STATE_COLORS.idle;
  const text = label || STATE_LABELS[state] || "READY";
  heroStatus.textContent = "●  " + text;
  heroStatus.style.background = colors.bg;
  heroStatus.style.color = colors.fg;
  const micBtn = document.getElementById("micBtn");
  micBtn.classList.toggle("listening", state === "listening");
};

window.jarvisSetStatusText = function (text) {
  statusText.textContent = text;
};

window.jarvisOnLevel = function (level) {
  S.micLevelRaw = level;
};

window.jarvisOnTtsLevel = function (level) {
  S.ttsLevel = level;
};

/* ============================================================
 * Sidebar navigation
 * ============================================================ */
const navList = document.getElementById("navList");
const navIndicator = document.getElementById("navIndicator");
const pages = {
  system: document.getElementById("page-system"),
  notes: document.getElementById("page-notes"),
  reminders: document.getElementById("page-reminders"),
  settings: document.getElementById("page-settings"),
};

function showPage(key, animateIndicator = true) {
  Object.entries(pages).forEach(([k, el]) => el.classList.toggle("active", k === key));
  navList.querySelectorAll(".nav-btn").forEach((btn) => {
    const active = btn.dataset.page === key;
    btn.classList.toggle("active", active);
    if (active) moveIndicator(btn, animateIndicator);
  });
  S.page = key;
}

function moveIndicator(btn) {
  navIndicator.style.top = btn.offsetTop + 6 + "px";
}

navList.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => showPage(btn.dataset.page));
});

window.addEventListener("resize", () => {
  const activeBtn = navList.querySelector(".nav-btn.active");
  if (activeBtn) moveIndicator(activeBtn);
});

/* ============================================================
 * Status dots / network badge
 * ============================================================ */
window.jarvisSetDot = function (key, value) {
  const el = document.querySelector(`.dot[data-dot="${key}"]`);
  if (!el) return;
  el.classList.toggle("on", !!value);
  el.classList.toggle("off", !value);
};

const netBadge = document.getElementById("netBadge");
window.jarvisSetNet = function (online) {
  netBadge.textContent = online ? "●  ONLINE" : "●  OFFLINE";
  netBadge.classList.toggle("online", !!online);
};

/* ============================================================
 * Mic / command input
 * ============================================================ */
const micBtn = document.getElementById("micBtn");
const sendBtn = document.getElementById("sendBtn");
const cmdInput = document.getElementById("cmdInput");

window.jarvisSetMicEnabled = function (enabled) {
  micBtn.disabled = !enabled;
  S.modelsReady = !!enabled || S.modelsReady;
};

micBtn.addEventListener("click", () => {
  window.pywebview.api.mic_input();
});

function sendCommand() {
  const text = cmdInput.value.trim();
  if (!text) return;
  cmdInput.value = "";
  window.pywebview.api.send_text(text);
}
sendBtn.addEventListener("click", sendCommand);
cmdInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendCommand(); });

// Text commands don't need the voice stack, so the mic button starts
// disabled and only opens up once GigaAM/VAD finish loading (or on first
// press, if wake word is off) — mirrors the old GUI's `self.mic.configure`.
window.jarvisSetMicEnabled(false);
micBtn.disabled = false; // allow the very first click to trigger lazy model load

/* ============================================================
 * Console log
 * ============================================================ */
const log = document.getElementById("log");
window.jarvisLogAdd = function (author, text) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  if (author === "ОШИБКА") entry.classList.add("log-err");
  if (author === "НАПОМИНАНИЕ") entry.classList.add("log-reminder");
  const a = document.createElement("span");
  a.className = "author";
  a.textContent = author;
  const p = document.createElement("p");
  p.textContent = text;
  entry.appendChild(a);
  entry.appendChild(p);
  log.appendChild(entry);
  while (log.children.length > LOG_MAX_ENTRIES) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
};

/* ============================================================
 * Toasts
 * ============================================================ */
window.jarvisToast = function (text) {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = text;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 2200);
};

window.jarvisReminderPopup = function (text) {
  const container = document.getElementById("reminderToastContainer");
  const el = document.createElement("div");
  el.className = "reminder-toast";
  el.textContent = "🔔  Напоминание: " + text;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 7000);
};

/* ============================================================
 * Notes
 * ============================================================ */
const notesBox = document.getElementById("notesBox");
const noteInput = document.getElementById("noteInput");
const addNoteBtn = document.getElementById("addNoteBtn");

let currentNotes = [];
let editingNoteId = null;
let editingDraft = "";

const ICON_EDIT =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const ICON_SAVE =
  '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

function makeIconBtn(className, title, html) {
  const btn = document.createElement("button");
  btn.className = className;
  btn.title = title;
  btn.innerHTML = html;
  return btn;
}

function startNoteEdit(note) {
  editingNoteId = note.id;
  editingDraft = note.text || "";
  renderNotes();
}

function cancelNoteEdit() {
  editingNoteId = null;
  editingDraft = "";
  renderNotes();
}

async function commitNoteEdit(note) {
  const text = editingDraft.trim();
  if (!text) {
    window.jarvisToast("Текст заметки не может быть пустым");
    return;
  }
  if (text === (note.text || "").trim()) {
    cancelNoteEdit();
    return;
  }
  const draft = editingDraft;
  editingNoteId = null;
  editingDraft = "";
  const editingRow = notesBox.querySelector(".list-row.editing");
  if (editingRow) editingRow.classList.add("removing");
  let result = null;
  try {
    result = await window.pywebview.api.edit_note_api(note.id, text);
  } catch (err) {
    result = { ok: false, error: String(err) };
  }
  if (!result || !result.ok) {
    // Не сохранилось — возвращаем поле редактирования с тем, что вводил пользователь.
    if (currentNotes.some((n) => n.id === note.id)) {
      editingNoteId = note.id;
      editingDraft = draft;
    }
    window.jarvisToast((result && result.error) || "Не удалось сохранить заметку");
    renderNotes();
  }
  // При успехе Python сам присылает обновлённый список (jarvisSetNotes).
}

function buildNoteViewRow(row, note, i) {
  const text = document.createElement("span");
  text.className = "list-row-text";
  text.textContent = `${i + 1}. ${note.text || ""}`;

  const actions = document.createElement("div");
  actions.className = "list-row-actions";

  const editBtn = makeIconBtn("list-row-edit", "Изменить заметку", ICON_EDIT);
  editBtn.addEventListener("click", () => startNoteEdit(note));

  const delBtn = document.createElement("button");
  delBtn.className = "list-row-del";
  delBtn.title = "Удалить заметку";
  delBtn.textContent = "✕";
  delBtn.addEventListener("click", async () => {
    row.classList.add("removing");
    const result = await window.pywebview.api.delete_note_api(note.id);
    if (!result || !result.ok) row.classList.remove("removing");
  });

  actions.appendChild(editBtn);
  actions.appendChild(delBtn);
  row.appendChild(text);
  row.appendChild(actions);
}

function buildNoteEditRow(row, note, i) {
  row.classList.add("editing");

  const index = document.createElement("span");
  index.className = "list-row-index";
  index.textContent = `${i + 1}.`;

  const input = document.createElement("input");
  input.type = "text";
  input.className = "list-row-input";
  input.value = editingDraft;
  input.addEventListener("input", () => { editingDraft = input.value; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commitNoteEdit(note); }
    else if (e.key === "Escape") { e.preventDefault(); cancelNoteEdit(); }
  });

  const actions = document.createElement("div");
  actions.className = "list-row-actions";
  const saveBtn = makeIconBtn("list-row-save", "Сохранить (Enter)", ICON_SAVE);
  saveBtn.addEventListener("click", () => commitNoteEdit(note));
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "list-row-cancel";
  cancelBtn.title = "Отмена (Esc)";
  cancelBtn.textContent = "✕";
  cancelBtn.addEventListener("click", cancelNoteEdit);
  actions.appendChild(saveBtn);
  actions.appendChild(cancelBtn);

  row.appendChild(index);
  row.appendChild(input);
  row.appendChild(actions);

  requestAnimationFrame(() => {
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  });
}

function renderNotes() {
  notesBox.innerHTML = "";
  if (!currentNotes.length) {
    notesBox.classList.add("empty");
    notesBox.textContent = "Заметок пока нет.";
    return;
  }
  notesBox.classList.remove("empty");
  currentNotes.forEach((note, i) => {
    const row = document.createElement("div");
    row.className = "list-row";
    if (note.id === editingNoteId) buildNoteEditRow(row, note, i);
    else buildNoteViewRow(row, note, i);
    notesBox.appendChild(row);
  });
}

window.jarvisSetNotes = function (notes) {
  currentNotes = notes || [];
  // Редактируемую заметку могли удалить голосом — сбрасываем режим правки.
  if (editingNoteId && !currentNotes.some((n) => n.id === editingNoteId)) {
    editingNoteId = null;
    editingDraft = "";
  }
  renderNotes();
};

addNoteBtn.addEventListener("click", async () => {
  const text = noteInput.value.trim();
  if (!text) return;
  noteInput.value = "";
  await window.pywebview.api.add_note_api(text);
});
noteInput.addEventListener("keydown", (e) => { if (e.key === "Enter") addNoteBtn.click(); });

/* ============================================================
 * Reminders
 * ============================================================ */
const remindersBox = document.getElementById("remindersBox");
const reminderInput = document.getElementById("reminderInput");
const reminderWhen = document.getElementById("reminderWhen");
const addReminderBtn = document.getElementById("addReminderBtn");

function formatDue(reminder) {
  if (reminder.due_at) {
    try {
      const d = new Date(reminder.due_at);
      const pad = (n) => String(n).padStart(2, "0");
      return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} в ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (e) { /* fall through */ }
  }
  return reminder.when || "";
}

window.jarvisSetReminders = function (reminders) {
  remindersBox.textContent = reminders.length
    ? reminders.map((r, i) => `${i + 1}. ${formatDue(r)} — ${r.text || ""}`).join("\n")
    : "Активных напоминаний нет.";
};

addReminderBtn.addEventListener("click", async () => {
  const text = reminderInput.value.trim();
  const when = reminderWhen.value.trim();
  if (!text || !when) return;
  reminderInput.value = "";
  reminderWhen.value = "";
  await window.pywebview.api.add_reminder_api(text, when);
});

/* ============================================================
 * Settings page
 * ============================================================ */
const modeSelect = document.getElementById("modeSelect");
const groqKey = document.getElementById("groqKey");
const groqModel = document.getElementById("groqModel");
const engineSelect = document.getElementById("engineSelect");
const wakeToggle = document.getElementById("wakeToggle");
const saveBtn = document.getElementById("saveBtn");

const cwav = document.getElementById("cwav");
const cdev = document.getElementById("cdev");
const clang = document.getElementById("clang");
const csplit = document.getElementById("csplit");
const ekey = document.getElementById("ekey");
const evoice = document.getElementById("evoice");
const emodel = document.getElementById("emodel");
const fkey = document.getElementById("fkey");
const fvoice = document.getElementById("fvoice");
const fmodel = document.getElementById("fmodel");
const speakerSelect = document.getElementById("speaker");
const sdev = document.getElementById("sdev");
const srate = document.getElementById("srate");

const ENGINE_PANELS = { coqui: "panel-coqui", elevenlabs: "panel-elevenlabs", fish_audio: "panel-fish_audio", silero: "panel-silero" };
const MASK = "•".repeat(16);

function showEnginePanel(key) {
  Object.entries(ENGINE_PANELS).forEach(([k, id]) => {
    document.getElementById(id).classList.toggle("hidden", k !== key);
  });
}
engineSelect.addEventListener("change", () => showEnginePanel(engineSelect.value));

function fillSelect(select, dict, selectedKey) {
  select.innerHTML = "";
  Object.entries(dict).forEach(([key, label]) => {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = label;
    if (key === selectedKey) opt.selected = true;
    select.appendChild(opt);
  });
}

function applyBootstrap(data) {
  const st = data.settings;

  fillSelect(modeSelect, data.performance_modes, st.performance_mode);
  fillSelect(engineSelect, data.tts_engines, st.tts_engine);
  fillSelect(speakerSelect, data.silero_speakers, st.silero_speaker);
  showEnginePanel(st.tts_engine);

  groqKey.value = data.groq_key_set ? MASK : "";
  groqModel.value = st.groq_model;
  ekey.value = data.eleven_key_set ? MASK : "";
  evoice.value = st.elevenlabs_voice_id;
  emodel.value = st.elevenlabs_model;
  fkey.value = data.fish_audio_key_set ? MASK : "";
  fvoice.value = st.fish_audio_voice_id || "";
  fmodel.value = st.fish_audio_model || "s2.1-pro";

  cwav.value = st.xtts_speaker_wav;
  cdev.value = st.xtts_device;
  clang.value = st.xtts_language;
  csplit.checked = !!st.xtts_split_sentences;

  sdev.value = st.silero_device;
  srate.value = String(st.silero_sample_rate);

  wakeToggle.checked = !!st.wake_word_enabled;

  document.getElementById("ttsEngineStat").textContent = data.tts_engines[st.tts_engine] || "Coqui XTTS-v2";

  window.jarvisSetNotes(data.notes || []);
  window.jarvisSetReminders(data.reminders || []);
}

saveBtn.addEventListener("click", async () => {
  const payload = {
    performance_mode: modeSelect.value,
    groq_api_key: groqKey.value.trim(),
    groq_model: groqModel.value.trim(),
    tts_engine: engineSelect.value,
    xtts_speaker_wav: cwav.value.trim(),
    xtts_device: cdev.value,
    xtts_language: clang.value.trim(),
    xtts_split_sentences: csplit.checked,
    elevenlabs_api_key: ekey.value.trim(),
    elevenlabs_voice_id: evoice.value.trim(),
    elevenlabs_model: emodel.value,
    fish_audio_api_key: fkey.value.trim(),
    fish_audio_voice_id: fvoice.value.trim(),
    fish_audio_model: fmodel.value,
    silero_speaker: speakerSelect.value,
    silero_device: sdev.value,
    silero_sample_rate: parseInt(srate.value, 10),
    wake_word_enabled: wakeToggle.checked,
  };
  const result = await window.pywebview.api.save_settings_api(payload);
  if (result && result.tts_engine_label) {
    document.getElementById("ttsEngineStat").textContent = result.tts_engine_label;
  }
});

/* ============================================================
 * Boot
 * ============================================================ */
function boot() {
  showPage("system", false);
  window.pywebview.api.get_bootstrap().then((data) => {
    applyBootstrap(data);
    window.pywebview.api.on_ready();
  });
}

if (window.pywebview) {
  boot();
} else {
  window.addEventListener("pywebviewready", boot);
}
