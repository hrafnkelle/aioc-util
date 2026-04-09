'use strict';

// ── Constants ──────────────────────────────────────────────────────────────
const AIOC_VID = 0x1209;
const AIOC_PID = 0x7388;

const Reg = {
  MAGIC:        0x00,
  USBID:        0x08,
  AIOC_IOMUX0:  0x24,
  AIOC_IOMUX1:  0x25,
  CM108_IOMUX0: 0x44,
  CM108_IOMUX1: 0x45,
  CM108_IOMUX2: 0x46,
  CM108_IOMUX3: 0x47,
  SERIAL_CTRL:  0x60,
  SERIAL_IOMUX0:0x64,
  SERIAL_IOMUX1:0x65,
  SERIAL_IOMUX2:0x66,
  SERIAL_IOMUX3:0x67,
  AUDIO_RX:     0x72,
  AUDIO_TX:     0x78,
  VPTT_LVLCTRL: 0x82,
  VPTT_TIMCTRL: 0x84,
  VCOS_LVLCTRL: 0x92,
  VCOS_TIMCTRL: 0x94,
  FOXHUNT_CTRL: 0xA0,
  FOXHUNT_MSG0: 0xA2,
  FOXHUNT_MSG1: 0xA3,
  FOXHUNT_MSG2: 0xA4,
  FOXHUNT_MSG3: 0xA5,
};

const Cmd = {
  NONE:        0x00,
  WRITESTROBE: 0x01,
  DEFAULTS:    0x10,
  REBOOT:      0x20,
  RECALL:      0x40,
  STORE:       0x80,
};

const PTTSourceBits = [
  { name: 'CM108GPIO1',    value: 0x00000001 },
  { name: 'CM108GPIO2',    value: 0x00000002 },
  { name: 'CM108GPIO3',    value: 0x00000004 },
  { name: 'CM108GPIO4',    value: 0x00000008 },
  { name: 'SERIALDTR',     value: 0x00000100 },
  { name: 'SERIALRTS',     value: 0x00000200 },
  { name: 'SERIALDTR~RTS', value: 0x00000400 },
  { name: 'SERIAL~DTRRTS', value: 0x00000800 },
  { name: 'VPTT',          value: 0x00001000 },
];

const CM108SrcBits = [
  { name: 'IN1',  value: 0x00010000 },
  { name: 'IN2',  value: 0x00020000 },
  { name: 'VCOS', value: 0x01000000 },
];

// PTT channel pin numbers (matching Python PTTChannel enum)
const PTTChannel = { PTT1: 3, PTT2: 4 };

// ── State ──────────────────────────────────────────────────────────────────
let device = null;

// ── Logging ────────────────────────────────────────────────────────────────
function log(msg, level = 'info') {
  const scrl = document.getElementById('log-scrl');
  const ts = new Date().toLocaleTimeString('en', { hour12: false, hour:'2-digit', minute:'2-digit', second:'2-digit' });
  const el = document.createElement('div');
  el.className = `le ${level}`;
  el.innerHTML = `<span class="ts">${ts}</span><span class="m">${escHtml(String(msg))}</span>`;
  scrl.appendChild(el);
  scrl.scrollTop = scrl.scrollHeight;
}
function logOk(m)   { log(m, 'ok');   }
function logWarn(m) { log(m, 'warn'); }
function logErr(m)  { log(m, 'err');  }

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── HID helpers ────────────────────────────────────────────────────────────
// Feature report layout (total 7 bytes including report ID 0):
//   [reportId=0, cmd, addr, val_LE_byte0, val_LE_byte1, val_LE_byte2, val_LE_byte3]
//
// sendFeatureReport(reportId=0, data) — data is 6 bytes WITHOUT the report ID.
// receiveFeatureReport(reportId=0)   — returned DataView INCLUDES reportId at [0].

async function regRead(addr) {
  const tx = new Uint8Array(6);
  tx[0] = Cmd.NONE;
  tx[1] = addr;
  // bytes 2-5 remain zero (value placeholder)
  await device.sendFeatureReport(0, tx);
  const dv = await device.receiveFeatureReport(0);
  // WebHID omits the report-ID byte for report ID 0 (unnamed report):
  //   6-byte response: [cmd_echo, addr_echo, v0, v1, v2, v3]  → value at offset 2
  //   7-byte response: [reportId, cmd_echo, addr_echo, v0, v1, v2, v3] → value at offset 3
  if (dv.byteLength < 6) throw new Error(`Short feature report: ${dv.byteLength} bytes`);
  const offset = dv.byteLength >= 7 ? 3 : 2;
  return dv.getUint32(offset, /*littleEndian=*/true);
}

async function regWrite(addr, value) {
  const tx = new Uint8Array(6);
  const dv = new DataView(tx.buffer);
  dv.setUint8(0, Cmd.WRITESTROBE);
  dv.setUint8(1, addr);
  dv.setUint32(2, value >>> 0, /*littleEndian=*/true);
  await device.sendFeatureReport(0, tx);
  log(`  wrote reg 0x${addr.toString(16).padStart(2,'0')} = 0x${(value >>> 0).toString(16).padStart(8,'0')}`);
}

async function sendCmd(cmd) {
  const tx = new Uint8Array(6);
  tx[0] = cmd;
  await device.sendFeatureReport(0, tx);
}

// PTT state via raw output report
// Python: Struct("<BBBBB").pack(0, 0, iodata, iomask, 0) → device.write(...)
async function setPTTState(pinNum, on) {
  const iomask = 1 << (pinNum - 1);
  const iodata = (on ? 1 : 0) << (pinNum - 1);
  // sendReport(reportId=0, data) — data does NOT include reportId
  await device.sendReport(0, new Uint8Array([0, iodata, iomask, 0]));
}

// ── UI helpers ─────────────────────────────────────────────────────────────
function setConnected(conn) {
  const dot   = document.getElementById('dot');
  const label = document.getElementById('conn-label');
  const btn   = document.getElementById('btn-connect');
  const prompt = document.getElementById('connect-prompt');
  dot.className   = 'dot' + (conn ? ' ok' : '');
  label.textContent = conn ? 'Connected' : 'Not connected';
  btn.textContent   = conn ? 'Disconnect' : 'Connect';
  btn.className     = conn ? 'btn btn-ghost' : 'btn btn-primary';
  prompt.style.display = conn ? 'none' : '';
  document.querySelectorAll('.needs-device').forEach(el => {
    el.classList.toggle('active', conn);
  });
}

function buildFlagGroup(containerId, bits, initialValue = 0) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  for (const bit of bits) {
    const chip = document.createElement('label');
    chip.className = 'flag-chip' + ((initialValue & bit.value) ? ' checked' : '');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = bit.value;
    cb.checked = !!(initialValue & bit.value);
    cb.addEventListener('change', () => {
      chip.classList.toggle('checked', cb.checked);
    });
    const txt = document.createElement('span');
    txt.textContent = bit.name;
    chip.appendChild(cb);
    chip.appendChild(txt);
    container.appendChild(chip);
  }
}

function readFlagGroup(containerId) {
  let val = 0;
  document.querySelectorAll(`#${containerId} input[type=checkbox]`).forEach(cb => {
    if (cb.checked) val |= parseInt(cb.value);
  });
  return val >>> 0;
}

function setFlagGroup(containerId, value) {
  document.querySelectorAll(`#${containerId} input[type=checkbox]`).forEach(cb => {
    const v = parseInt(cb.value);
    cb.checked = !!(value & v);
    cb.closest('.flag-chip').classList.toggle('checked', cb.checked);
  });
}

function parseHex(str, fallback = 0) {
  const v = parseInt(str, str.startsWith('0x') || str.startsWith('0X') ? 16 : 10);
  return isNaN(v) ? fallback : v;
}

function fmtHex(v) { return '0x' + (v >>> 0).toString(16).padStart(8,'0'); }

function pttSourceName(val) {
  const parts = PTTSourceBits.filter(b => (val & b.value) !== 0).map(b => b.name);
  return parts.length ? parts.join(' | ') : 'NONE';
}
function cm108SrcName(val) {
  const parts = CM108SrcBits.filter(b => (val & b.value) !== 0).map(b => b.name);
  return parts.length ? parts.join(' | ') : 'NONE';
}

// ── Build flag groups ──────────────────────────────────────────────────────
buildFlagGroup('ptt1-flags',       PTTSourceBits);
buildFlagGroup('ptt2-flags',       PTTSourceBits);
buildFlagGroup('cm108-btn1-flags', CM108SrcBits);
buildFlagGroup('cm108-btn2-flags', CM108SrcBits);
buildFlagGroup('cm108-btn3-flags', CM108SrcBits);
buildFlagGroup('cm108-btn4-flags', CM108SrcBits);

// ── Connect / Disconnect ───────────────────────────────────────────────────
async function connect() {
  if (!navigator.hid) {
    logErr('WebHID is not available. Use Chrome/Edge 89+ over HTTPS or localhost.');
    return;
  }
  try {
    const devices = await navigator.hid.requestDevice({
      filters: [{ vendorId: AIOC_VID, productId: AIOC_PID }]
    });
    if (!devices.length) { log('No device selected.'); return; }

    // Try each returned collection, verify magic
    for (const d of devices) {
      if (!d.opened) await d.open();
      // Read MAGIC register
      try {
        const magic = await readRegWithDevice(d, Reg.MAGIC);
        const bytes = new Uint8Array(4);
        new DataView(bytes.buffer).setUint32(0, magic, true); // little-endian matches register byte order
        const text = String.fromCharCode(...bytes);
        if (text !== 'AIOC') {
          logWarn(`Device magic: "${text}" — expected "AIOC". Skipping this collection.`);
          await d.close();
          continue;
        }
        device = d;
        logOk(`Connected: ${d.productName || 'AIOC'} (magic OK: "${text}")`);
        setConnected(true);
        populateDeviceInfo();
        await readAll();
        return;
      } catch(e) {
        logWarn(`Collection failed: ${e.message}`);
        try { await d.close(); } catch(_) {}
      }
    }
    logErr('Could not find a valid AIOC configuration interface.');
  } catch(e) {
    logErr('Connect failed: ' + e.message);
  }
}

// Helper: read from a specific device object (used during connect before device is assigned)
async function readRegWithDevice(d, addr) {
  const tx = new Uint8Array(6);
  tx[0] = Cmd.NONE; tx[1] = addr;
  await d.sendFeatureReport(0, tx);
  const dv = await d.receiveFeatureReport(0);
  if (dv.byteLength < 6) throw new Error(`Short report: ${dv.byteLength}b`);
  const offset = dv.byteLength >= 7 ? 3 : 2;
  return dv.getUint32(offset, true);
}

async function disconnect() {
  if (device) {
    try { await device.close(); } catch(_) {}
    device = null;
    log('Disconnected.');
    setConnected(false);
  }
}

function populateDeviceInfo() {
  // WebHID HIDDevice exposes: productName, vendorId, productId only
  document.getElementById('i-prod').textContent  = device.productName || '—';
  document.getElementById('i-vidpid').textContent =
    `${device.vendorId.toString(16).toUpperCase().padStart(4,'0')}:${device.productId.toString(16).toUpperCase().padStart(4,'0')}`;
}

// ── Read All ───────────────────────────────────────────────────────────────
async function readAll() {
  if (!device) return;
  log('Reading all settings…');
  try {
    // Magic
    const magic = await regRead(Reg.MAGIC);
    const mb = new Uint8Array(4);
    new DataView(mb.buffer).setUint32(0, magic, true); // little-endian matches register byte order
    document.getElementById('i-magic').textContent = `"${String.fromCharCode(...mb)}" (${fmtHex(magic)})`;

    // PTT sources
    const ptt1 = await regRead(Reg.AIOC_IOMUX0);
    const ptt2 = await regRead(Reg.AIOC_IOMUX1);
    setFlagGroup('ptt1-flags', ptt1);
    setFlagGroup('ptt2-flags', ptt2);
    log(`  PTT1: ${pttSourceName(ptt1)}  PTT2: ${pttSourceName(ptt2)}`);

    // CM108 buttons
    const b1 = await regRead(Reg.CM108_IOMUX0);
    const b2 = await regRead(Reg.CM108_IOMUX1);
    const b3 = await regRead(Reg.CM108_IOMUX2);
    const b4 = await regRead(Reg.CM108_IOMUX3);
    setFlagGroup('cm108-btn1-flags', b1);
    setFlagGroup('cm108-btn2-flags', b2);
    setFlagGroup('cm108-btn3-flags', b3);
    setFlagGroup('cm108-btn4-flags', b4);
    log(`  Vol↑: ${cm108SrcName(b1)}  Vol↓: ${cm108SrcName(b2)}`);

    // Audio
    const rx = await regRead(Reg.AUDIO_RX);
    const tx = await regRead(Reg.AUDIO_TX);
    document.getElementById('sel-rxgain').value  = String(rx & 0x0F);
    document.getElementById('sel-txboost').value = String(tx & 0x100 ? 256 : 0);
    log(`  Audio RX gain: ${['1×','2×','4×','8×','16×'][rx & 0x0F] || '?'}  TX boost: ${(tx & 0x100) ? 'on' : 'off'}`);

    // VPTT / VCOS
    const vpttLvl = await regRead(Reg.VPTT_LVLCTRL);
    const vpttTim = await regRead(Reg.VPTT_TIMCTRL);
    const vcosLvl = await regRead(Reg.VCOS_LVLCTRL);
    const vcosTim = await regRead(Reg.VCOS_TIMCTRL);
    document.getElementById('vptt-lvl').value = String(vpttLvl >>> 0);
    document.getElementById('vptt-tim').value = String(vpttTim >>> 0);
    document.getElementById('vcos-lvl').value = String(vcosLvl >>> 0);
    document.getElementById('vcos-tim').value = String(vcosTim >>> 0);

    // Foxhunt
    const foxCtrl = await regRead(Reg.FOXHUNT_CTRL);
    document.getElementById('fox-vol').value      = (foxCtrl >> 16) & 0xFFFF;
    document.getElementById('fox-wpm').value      = (foxCtrl >> 8)  & 0xFF;
    document.getElementById('fox-interval').value = (foxCtrl >> 0)  & 0xFF;

    // Foxhunt message
    const msgBytes = [];
    for (const reg of [Reg.FOXHUNT_MSG0, Reg.FOXHUNT_MSG1, Reg.FOXHUNT_MSG2, Reg.FOXHUNT_MSG3]) {
      const v = await regRead(reg);
      const b = new Uint8Array(4);
      new DataView(b.buffer).setUint32(0, v, true); // little-endian
      msgBytes.push(...b);
    }
    const nullIdx = msgBytes.indexOf(0);
    const msgArr  = nullIdx >= 0 ? msgBytes.slice(0, nullIdx) : msgBytes;
    document.getElementById('fox-msg').value = String.fromCharCode(...msgArr.filter(c => c >= 32 && c < 127));

    logOk('All settings read successfully.');
  } catch(e) {
    logErr('Read error: ' + e.message);
    console.error(e);
  }
}

// ── PTT Write ──────────────────────────────────────────────────────────────
async function writePTT() {
  if (!device) return;
  try {
    const p1 = readFlagGroup('ptt1-flags');
    const p2 = readFlagGroup('ptt2-flags');
    log(`Writing PTT1=${pttSourceName(p1)}, PTT2=${pttSourceName(p2)}`);
    await regWrite(Reg.AIOC_IOMUX0, p1);
    await regWrite(Reg.AIOC_IOMUX1, p2);
    logOk('PTT sources written.');
  } catch(e) { logErr(e.message); }
}

async function readPTT() {
  if (!device) return;
  try {
    const p1 = await regRead(Reg.AIOC_IOMUX0);
    const p2 = await regRead(Reg.AIOC_IOMUX1);
    setFlagGroup('ptt1-flags', p1);
    setFlagGroup('ptt2-flags', p2);
    logOk(`PTT1: ${pttSourceName(p1)}  PTT2: ${pttSourceName(p2)}`);
  } catch(e) { logErr(e.message); }
}

async function swapPTT() {
  if (!device) return;
  try {
    const p1 = await regRead(Reg.AIOC_IOMUX0);
    const p2 = await regRead(Reg.AIOC_IOMUX1);
    log(`Swapping: PTT1 ← ${pttSourceName(p2)}, PTT2 ← ${pttSourceName(p1)}`);
    await regWrite(Reg.AIOC_IOMUX0, p2);
    await regWrite(Reg.AIOC_IOMUX1, p1);
    setFlagGroup('ptt1-flags', p2);
    setFlagGroup('ptt2-flags', p1);
    logOk('PTT swapped.');
  } catch(e) { logErr(e.message); }
}

async function autoPTT1() {
  if (!device) return;
  const VPTT = 0x00001000;
  try {
    log('Setting PTT1 → VPTT');
    await regWrite(Reg.AIOC_IOMUX0, VPTT);
    setFlagGroup('ptt1-flags', VPTT);
    logOk('PTT1 set to VPTT (AutoPTT).');
  } catch(e) { logErr(e.message); }
}

// ── CM108 Buttons Write ────────────────────────────────────────────────────
async function writeButtons() {
  if (!device) return;
  try {
    const b1 = readFlagGroup('cm108-btn1-flags');
    const b2 = readFlagGroup('cm108-btn2-flags');
    const b3 = readFlagGroup('cm108-btn3-flags');
    const b4 = readFlagGroup('cm108-btn4-flags');
    log(`Writing CM108 buttons: B1=${cm108SrcName(b1)} B2=${cm108SrcName(b2)} B3=${cm108SrcName(b3)} B4=${cm108SrcName(b4)}`);
    await regWrite(Reg.CM108_IOMUX0, b1);
    await regWrite(Reg.CM108_IOMUX1, b2);
    await regWrite(Reg.CM108_IOMUX2, b3);
    await regWrite(Reg.CM108_IOMUX3, b4);
    logOk('Button sources written.');
  } catch(e) { logErr(e.message); }
}

async function readButtons() {
  if (!device) return;
  try {
    setFlagGroup('cm108-btn1-flags', await regRead(Reg.CM108_IOMUX0));
    setFlagGroup('cm108-btn2-flags', await regRead(Reg.CM108_IOMUX1));
    setFlagGroup('cm108-btn3-flags', await regRead(Reg.CM108_IOMUX2));
    setFlagGroup('cm108-btn4-flags', await regRead(Reg.CM108_IOMUX3));
    logOk('Button sources read.');
  } catch(e) { logErr(e.message); }
}

async function enableVCOS() {
  if (!device) return;
  try {
    log('Enabling virtual COS: VolUp←IN2, VolDn←VCOS');
    await regWrite(Reg.CM108_IOMUX0, 0x00020000); // IN2
    await regWrite(Reg.CM108_IOMUX1, 0x01000000); // VCOS
    setFlagGroup('cm108-btn1-flags', 0x00020000);
    setFlagGroup('cm108-btn2-flags', 0x01000000);
    logOk('Virtual COS enabled.');
  } catch(e) { logErr(e.message); }
}

async function enableHWCOS() {
  if (!device) return;
  try {
    log('Enabling hardware COS: VolUp←NONE, VolDn←IN2');
    await regWrite(Reg.CM108_IOMUX0, 0x00000000); // NONE
    await regWrite(Reg.CM108_IOMUX1, 0x00020000); // IN2
    setFlagGroup('cm108-btn1-flags', 0x00000000);
    setFlagGroup('cm108-btn2-flags', 0x00020000);
    logOk('Hardware COS enabled.');
  } catch(e) { logErr(e.message); }
}

// ── Audio Write ────────────────────────────────────────────────────────────
async function writeAudio() {
  if (!device) return;
  try {
    const rx = parseInt(document.getElementById('sel-rxgain').value);
    const tx = parseInt(document.getElementById('sel-txboost').value);
    log(`Writing audio: RX gain=${['1×','2×','4×','8×','16×'][rx]}, TX boost=${tx ? 'on' : 'off'}`);
    await regWrite(Reg.AUDIO_RX, rx);
    await regWrite(Reg.AUDIO_TX, tx);
    logOk('Audio settings written.');
  } catch(e) { logErr(e.message); }
}

async function readAudio() {
  if (!device) return;
  try {
    const rx = await regRead(Reg.AUDIO_RX);
    const tx = await regRead(Reg.AUDIO_TX);
    document.getElementById('sel-rxgain').value  = String(rx & 0x0F);
    document.getElementById('sel-txboost').value = String(tx & 0x100 ? 256 : 0);
    logOk(`Audio: RX=${['1×','2×','4×','8×','16×'][rx & 0x0F]} TX boost=${(tx & 0x100) ? 'on' : 'off'}`);
  } catch(e) { logErr(e.message); }
}

// ── VPTT / VCOS Write ──────────────────────────────────────────────────────
async function writeAVCOS() {
  if (!device) return;
  try {
    const vpttLvl = parseHex(document.getElementById('vptt-lvl').value);
    const vpttTim = parseHex(document.getElementById('vptt-tim').value);
    const vcosLvl = parseHex(document.getElementById('vcos-lvl').value);
    const vcosTim = parseHex(document.getElementById('vcos-tim').value);
    log(`Writing VPTT/VCOS thresholds…`);
    await regWrite(Reg.VPTT_LVLCTRL, vpttLvl);
    await regWrite(Reg.VPTT_TIMCTRL, vpttTim);
    await regWrite(Reg.VCOS_LVLCTRL, vcosLvl);
    await regWrite(Reg.VCOS_TIMCTRL, vcosTim);
    logOk('VPTT/VCOS thresholds written.');
  } catch(e) { logErr(e.message); }
}

async function readAVCOS() {
  if (!device) return;
  try {
    document.getElementById('vptt-lvl').value = String(await regRead(Reg.VPTT_LVLCTRL) >>> 0);
    document.getElementById('vptt-tim').value = String(await regRead(Reg.VPTT_TIMCTRL) >>> 0);
    document.getElementById('vcos-lvl').value = String(await regRead(Reg.VCOS_LVLCTRL) >>> 0);
    document.getElementById('vcos-tim').value = String(await regRead(Reg.VCOS_TIMCTRL) >>> 0);
    logOk('VPTT/VCOS thresholds read.');
  } catch(e) { logErr(e.message); }
}

// ── Foxhunt Write ──────────────────────────────────────────────────────────
async function writeFoxhunt() {
  if (!device) return;
  try {
    const vol      = Math.min(65535, Math.max(0, parseInt(document.getElementById('fox-vol').value)      || 0));
    const wpm      = Math.min(255,   Math.max(0, parseInt(document.getElementById('fox-wpm').value)      || 0));
    const interval = Math.min(255,   Math.max(0, parseInt(document.getElementById('fox-interval').value) || 0));
    const ctrl = ((vol & 0xFFFF) << 16) | ((wpm & 0xFF) << 8) | (interval & 0xFF);
    log(`Writing foxhunt: vol=${vol} wpm=${wpm} interval=${interval}s`);
    await regWrite(Reg.FOXHUNT_CTRL, ctrl >>> 0);

    // Message
    const msg = document.getElementById('fox-msg').value.substring(0, 16);
    const msgBytes = new Uint8Array(16);
    for (let i = 0; i < msg.length; i++) msgBytes[i] = msg.charCodeAt(i) & 0x7F;
    log(`Writing foxhunt message: "${msg}"`);
    const regs = [Reg.FOXHUNT_MSG0, Reg.FOXHUNT_MSG1, Reg.FOXHUNT_MSG2, Reg.FOXHUNT_MSG3];
    for (let i = 0; i < 4; i++) {
      const dv = new DataView(msgBytes.buffer, i * 4, 4);
      await regWrite(regs[i], dv.getUint32(0, true));
    }
    logOk('Foxhunt settings written.');
  } catch(e) { logErr(e.message); }
}

async function readFoxhunt() {
  if (!device) return;
  try {
    const ctrl = await regRead(Reg.FOXHUNT_CTRL);
    document.getElementById('fox-vol').value      = (ctrl >> 16) & 0xFFFF;
    document.getElementById('fox-wpm').value      = (ctrl >> 8)  & 0xFF;
    document.getElementById('fox-interval').value = (ctrl >> 0)  & 0xFF;

    const msgBytes = [];
    for (const reg of [Reg.FOXHUNT_MSG0, Reg.FOXHUNT_MSG1, Reg.FOXHUNT_MSG2, Reg.FOXHUNT_MSG3]) {
      const v = await regRead(reg);
      const b = new Uint8Array(4);
      new DataView(b.buffer).setUint32(0, v, true);
      msgBytes.push(...b);
    }
    const nullIdx = msgBytes.indexOf(0);
    const arr = nullIdx >= 0 ? msgBytes.slice(0, nullIdx) : msgBytes;
    document.getElementById('fox-msg').value = String.fromCharCode(...arr.filter(c => c >= 32 && c < 127));
    logOk('Foxhunt settings read.');
  } catch(e) { logErr(e.message); }
}

// ── USB ID Write ───────────────────────────────────────────────────────────
async function writeUSBID() {
  if (!device) return;
  const vidStr = document.getElementById('usb-vid').value.trim();
  const pidStr = document.getElementById('usb-pid').value.trim();
  const vid = parseHex(vidStr);
  const pid = parseHex(pidStr);
  if (!vid || !pid) { logErr('Invalid VID or PID.'); return; }
  if (!confirm(`Set USB VID:PID to ${vid.toString(16).padStart(4,'0')}:${pid.toString(16).padStart(4,'0')}?\n\nThis requires a Store + Reboot to take effect. Proceed?`)) return;
  try {
    const value = ((pid & 0xFFFF) << 16) | (vid & 0xFFFF);
    log(`Writing USBID: VID=0x${vid.toString(16)} PID=0x${pid.toString(16)} → ${fmtHex(value)}`);
    await regWrite(Reg.USBID, value >>> 0);
    logOk('USB ID written. Remember to Store and Reboot.');
  } catch(e) { logErr(e.message); }
}

// ── Register Dump ──────────────────────────────────────────────────────────
async function dumpRegisters() {
  if (!device) return;
  const tbody = document.getElementById('reg-tbody');
  tbody.innerHTML = '';
  for (const [name, addr] of Object.entries(Reg)) {
    try {
      const v = await regRead(addr);
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${name}</td><td>0x${addr.toString(16).padStart(2,'0')}</td><td>${fmtHex(v)}</td>`;
      tbody.appendChild(tr);
    } catch(e) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${name}</td><td>0x${addr.toString(16).padStart(2,'0')}</td><td style="color:var(--red)">error</td>`;
      tbody.appendChild(tr);
    }
  }
  logOk('Register dump complete.');
}

// Device commands
async function deviceCmd(cmd, label) {
  if (!device) return;
  log(`Sending command: ${label}…`);
  try {
    await sendCmd(cmd);
    logOk(`${label} command sent.`);
  } catch(e) { logErr(e.message); }
}

// ── Connect button ─────────────────────────────────────────────────────────
document.getElementById('btn-connect').addEventListener('click', () => {
  if (device) disconnect(); else connect();
});

// Auto-disconnect on page unload
window.addEventListener('beforeunload', () => {
  if (device) try { device.close(); } catch(_) {}
});

// Handle disconnect from OS side
if (navigator.hid) {
  navigator.hid.addEventListener('disconnect', ({ device: d }) => {
    if (device && d === device) {
      device = null;
      log('Device disconnected.', 'warn');
      setConnected(false);
    }
  });
}

// ── Wire up all buttons ────────────────────────────────────────────────────
document.getElementById('btn-read-all').addEventListener('click', readAll);

// PTT
document.getElementById('btn-ptt-read').addEventListener('click',  readPTT);
document.getElementById('btn-ptt-write').addEventListener('click', writePTT);
document.getElementById('btn-swap-ptt').addEventListener('click',  swapPTT);
document.getElementById('btn-auto-ptt1').addEventListener('click', autoPTT1);

// Buttons
document.getElementById('btn-btn-read').addEventListener('click',       readButtons);
document.getElementById('btn-btn-write').addEventListener('click',      writeButtons);
document.getElementById('btn-enable-vcos').addEventListener('click',    enableVCOS);
document.getElementById('btn-enable-hwcos').addEventListener('click',   enableHWCOS);

// Audio
document.getElementById('btn-audio-read').addEventListener('click',  readAudio);
document.getElementById('btn-audio-write').addEventListener('click', writeAudio);

// VPTT/VCOS
document.getElementById('btn-avcos-read').addEventListener('click',  readAVCOS);
document.getElementById('btn-avcos-write').addEventListener('click', writeAVCOS);

// Foxhunt
document.getElementById('btn-fox-read').addEventListener('click',  readFoxhunt);
document.getElementById('btn-fox-write').addEventListener('click', writeFoxhunt);

// PTT state
document.getElementById('btn-ptt1-on').addEventListener('click',  () => setPTTState(PTTChannel.PTT1, true).then(() => logOk('PTT1 ON')).catch(e => logErr(e.message)));
document.getElementById('btn-ptt1-off').addEventListener('click', () => setPTTState(PTTChannel.PTT1, false).then(() => logOk('PTT1 OFF')).catch(e => logErr(e.message)));
document.getElementById('btn-ptt2-on').addEventListener('click',  () => setPTTState(PTTChannel.PTT2, true).then(() => logOk('PTT2 ON')).catch(e => logErr(e.message)));
document.getElementById('btn-ptt2-off').addEventListener('click', () => setPTTState(PTTChannel.PTT2, false).then(() => logOk('PTT2 OFF')).catch(e => logErr(e.message)));

// USB ID
document.getElementById('btn-usb-write').addEventListener('click', writeUSBID);

// Dump
document.getElementById('btn-dump').addEventListener('click', dumpRegisters);

// Device commands
document.getElementById('btn-store').addEventListener('click',    () => {
  if (!confirm('Store current settings to flash?')) return;
  deviceCmd(Cmd.STORE, 'Store');
});
document.getElementById('btn-recall').addEventListener('click',   () => deviceCmd(Cmd.RECALL,   'Recall'));
document.getElementById('btn-defaults').addEventListener('click', () => {
  if (!confirm('Load factory defaults? This will overwrite current settings.')) return;
  deviceCmd(Cmd.DEFAULTS, 'Defaults');
});
document.getElementById('btn-reboot').addEventListener('click',   () => {
  if (!confirm('Reboot the AIOC device?')) return;
  deviceCmd(Cmd.REBOOT, 'Reboot');
});

// Log clear
document.getElementById('btn-clrlog').addEventListener('click', () => {
  document.getElementById('log-scrl').innerHTML = '';
});

// ── Initial state ──────────────────────────────────────────────────────────
setConnected(false);
log('AIOC Utility ready. Click Connect to open the device.');
if (!navigator.hid) {
  logErr('WebHID is not supported in this browser. Use a compatible browser on a desktop computer.');
}