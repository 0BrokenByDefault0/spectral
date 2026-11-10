/* Spectral — navigation, figures and interactive tools. */
(function () {
  const D = window.SPECTRAL;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const view = $('#view');
  const tabsEl = $('#tabs');
  const lessonEl = $('#lesson');
  const ALL = D.tracks.flatMap((t) => t.lessons.map((l) => ({ ...l, track: t })));

  /* ---------- storage ---------- */
  const store = {
    get(k, d) { try { const v = localStorage.getItem('spectral.' + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('spectral.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const done = new Set(store.get('done', []));
  const checks = store.get('checks', {});
  const haptic = (k = 'light') => { try { window.webkit.messageHandlers.haptic.postMessage(k); } catch (e) { /* not in app */ } };

  /* ---------- icons ---------- */
  const I = {
    home: '<path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4v-5h-6v5H5a1 1 0 0 1-1-1z"/>',
    record: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6"/>',
    mix: '<path d="M6 4v16M12 4v16M18 4v16"/><rect x="4" y="13" width="4" height="3.4" rx="1" fill="currentColor"/><rect x="10" y="6.5" width="4" height="3.4" rx="1" fill="currentColor"/><rect x="16" y="10.5" width="4" height="3.4" rx="1" fill="currentColor"/>',
    tools: '<path d="M3 12h3l2.5-6 4 13 3-9 1.5 2H21"/>',
    glossary: '<path d="M5 4.5h10a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M9 9h5M9 12.5h5"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    next: '<path d="M9 5l7 7-7 7"/>',
    check: '<path d="M4 12.5l5 5L20 6.5"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>',
    wave: '<path d="M3 12c2-7 4-7 6 0s4 7 6 0 4-7 6 0"/>',
  };
  const svg = (name) => `<svg viewBox="0 0 24 24">${I[name]}</svg>`;

  /* ---------- figures ---------- */
  const B = '#5b8cff', BH = '#93b9ff', O = '#ff8f3f', OH = '#ffc078', M = '#9ba9d1', L = 'rgba(140,170,255,.22)';
  const fx = (f, w = 320, pad = 8) => pad + ((Math.log10(f) - Math.log10(20)) / 3) * (w - pad * 2);
  const txt = (x, y, s, o = {}) => `<text x="${x}" y="${y}" fill="${o.fill || M}" font-size="${o.size || 10}" font-weight="${o.w || 500}" text-anchor="${o.a || 'middle'}">${s}</text>`;

  const FIG = {
    chain() {
      const n = [['Voice', O], ['Mic', O], ['Preamp', B], ['Converter', B], ['DAW', B]];
      return `<svg viewBox="0 0 320 96">${n.map(([t, c], i) => {
        const x = 8 + i * 63;
        return `<rect x="${x}" y="30" width="52" height="38" rx="11" fill="${c}22" stroke="${c}" stroke-width="1.2"/>${txt(x + 26, 53, t, { fill: '#eaf0ff', size: 10.5, w: 650 })}${i < 4 ? `<path d="M${x + 54} 49h7" stroke="${M}" stroke-width="1.4" stroke-linecap="round"/><path d="M${x + 59} 46l3 3-3 3" fill="none" stroke="${M}" stroke-width="1.4" stroke-linecap="round"/>` : ''}`;
      }).join('')}${txt(60, 20, 'AIR → ELECTRICITY', { size: 8.5, fill: OH, w: 700 })}${txt(223, 20, 'AUDIO INTERFACE + COMPUTER', { size: 8.5, fill: BH, w: 700 })}<path d="M134 84h115" stroke="${B}" stroke-width="1" stroke-dasharray="3 3"/>${txt(191, 94, 'one box', { size: 8.5 })}</svg>`;
    },
    room() {
      return `<svg viewBox="0 0 320 200"><rect x="20" y="14" width="280" height="172" rx="8" fill="rgba(91,140,255,.05)" stroke="${L}" stroke-width="1.5"/>
      <rect x="196" y="20" width="98" height="10" rx="5" fill="${B}" opacity=".75"/><rect x="284" y="20" width="10" height="92" rx="5" fill="${B}" opacity=".75"/>${txt(238, 46, 'duvet / absorption', { size: 9, fill: BH })}
      <circle cx="238" cy="78" r="13" fill="${O}33" stroke="${O}" stroke-width="1.5"/>${txt(238, 81.5, 'you', { size: 9, fill: '#fff', w: 700 })}
      <path d="M229 88l-22 26" stroke="${OH}" stroke-width="1.2" stroke-dasharray="3 3"/><rect x="194" y="112" width="14" height="14" rx="4" fill="${OH}"/>${txt(176, 123, 'mic', { size: 9, fill: OH })}
      <rect x="150" y="132" width="110" height="40" rx="6" fill="none" stroke="${L}" stroke-dasharray="4 4"/>${txt(205, 156, 'rug', { size: 9 })}
      <circle cx="160" cy="100" r="5" fill="none" stroke="#ff9c9c"/><path d="M156.500 96.500l7 7M163.500 96.500l-7 7" stroke="#ff9c9c"/>${txt(160, 88, 'not dead centre', { size: 8.5, fill: '#ff9c9c' })}
      <rect x="34" y="146" width="44" height="26" rx="5" fill="rgba(255,255,255,.06)" stroke="${L}"/>${txt(56, 162, 'laptop', { size: 8.5 })}
      <path d="M192 124 82 152" stroke="${M}" stroke-width=".8" stroke-dasharray="2 4"/>${txt(124, 131, 'back of mic faces noise', { size: 8.5 })}</svg>`;
    },
    polar() {
      let d = '';
      for (let a = 0; a <= 360; a += 4) { const r = 54 * (0.5 + 0.5 * Math.cos((a * Math.PI) / 180)); const x = 160 + r * Math.sin((a * Math.PI) / 180), y = 104 - r * Math.cos((a * Math.PI) / 180) * 1.0; d += `${a ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`; }
      return `<svg viewBox="0 0 320 180">${[18, 36, 54].map((r) => `<circle cx="160" cy="104" r="${r}" fill="none" stroke="${L}"/>`).join('')}<path d="M160 44v120M100 104h120" stroke="${L}"/><path d="${d}Z" fill="${O}2e" stroke="${O}" stroke-width="2"/><rect x="153" y="96" width="14" height="18" rx="6" fill="#eaf0ff"/>
      ${txt(160, 30, 'FRONT · full pickup', { fill: OH, w: 700, size: 9.5 })}${txt(160, 176, 'BACK · rejected', { fill: BH, w: 700, size: 9.5 })}${txt(60, 107, 'sides quieter', { size: 9 })}${txt(262, 107, 'sides quieter', { size: 9 })}</svg>`;
    },
    placement() {
      return `<svg viewBox="0 0 320 170"><path d="M38 150V84a34 34 0 0 1 34-34h6a30 30 0 0 1 30 30v10l10 14-10 4v14a12 12 0 0 1-12 12H84v16" fill="${B}1f" stroke="${BH}" stroke-width="1.6" stroke-linejoin="round"/>
      <path d="M112 106c16-5 30-6 44-6" stroke="${OH}" stroke-width="1.1" stroke-dasharray="2 4"/>
      <ellipse cx="196" cy="100" rx="3.500" ry="27" fill="${O}33" stroke="${O}" stroke-width="1.4"/>${txt(196, 62, 'pop filter', { size: 9, fill: OH })}
      <rect x="240" y="74" width="26" height="48" rx="12" fill="#eaf0ff18" stroke="#eaf0ff" stroke-width="1.6"/><path d="M240 92h26M240 100h26" stroke="#eaf0ff" stroke-width=".8" opacity=".6"/><path d="M253 122v40M238 162h30" stroke="#eaf0ff" stroke-width="1.6" stroke-linecap="round"/>
      <path d="M120 140h118" stroke="${BH}" stroke-width="1"/><path d="M120 135v10M238 135v10" stroke="${BH}"/>${txt(179, 155, '10–20 cm', { fill: BH, w: 700, size: 10.5 })}
      <path d="M200 40h38" stroke="${OH}" stroke-width="1"/><path d="M200 35v10M238 35v10" stroke="${OH}"/>${txt(219, 30, '5–8 cm', { fill: OH, w: 700, size: 10.5 })}
      ${txt(292, 100, 'capsule', { size: 8.5 })}${txt(292, 111, 'at lip–nose', { size: 8.5 })}</svg>`;
    },
    meter() {
      const y = (db) => 18 + (-db / 60) * 150;
      const lab = (db, t, c) => `<path d="M118 ${y(db)}h10" stroke="${c}"/>${txt(134, y(db) + 3.5, `${db === 0 ? '0' : '−' + -db} dBFS`, { a: 'start', fill: '#eaf0ff', w: 700, size: 10 })}${txt(196, y(db) + 3.5, t, { a: 'start', size: 9.5, fill: c })}`;
      return `<svg viewBox="0 0 320 186"><defs><linearGradient id="mg" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="${B}" stop-opacity=".35"/><stop offset=".62" stop-color="${B}"/><stop offset=".86" stop-color="${O}"/><stop offset="1" stop-color="#ff5d5d"/></linearGradient></defs>
      <rect x="62" y="18" width="22" height="150" rx="6" fill="rgba(255,255,255,.05)"/><rect x="90" y="18" width="22" height="150" rx="6" fill="rgba(255,255,255,.05)"/>
      <rect x="62" y="${y(-9)}" width="22" height="${168 - y(-9)}" rx="6" fill="url(#mg)"/><rect x="90" y="${y(-12)}" width="22" height="${168 - y(-12)}" rx="6" fill="url(#mg)"/>
      ${lab(0, 'clipping. Never.', '#ff9c9c')}${lab(-8, 'loudest peaks, −10 to −6', OH)}${lab(-18, 'average level', BH)}${lab(-40, 'quiet detail, still clean', M)}${lab(-60, 'noise floor', M)}</svg>`;
    },
    mixchain() {
      const s = ['Edit', 'Clip gain', 'Tune', 'EQ cut', 'Compress', 'De-ess', 'EQ boost', 'Saturate', 'Reverb + delay', 'Automate'];
      return `<div class="flow">${s.map((x, i) => `<span>${x}</span>${i < s.length - 1 ? '<i>→</i>' : ''}`).join('')}</div>`;
    },
    pocket() {
      const W = 320, base = 62;
      let beat = '', vox = '';
      for (let x = 8; x <= 312; x += 4) {
        const f = 20 * Math.pow(1000, (x - 8) / 304), lf = Math.log10(f);
        const dip = 20 * Math.exp(-Math.pow((lf - Math.log10(2800)) / 0.22, 2));
        const edge = 26 * Math.exp(-Math.pow((lf - 1.3) / 0.16, 2)) + 30 * Math.exp(-Math.pow((lf - 4.3) / 0.14, 2));
        beat += `${x === 8 ? 'M' : 'L'}${x} ${(base + dip + edge).toFixed(1)}`;
        const v = 52 * Math.exp(-Math.pow((lf - Math.log10(2600)) / 0.36, 2)) + 14 * Math.exp(-Math.pow((lf - Math.log10(300)) / 0.3, 2));
        vox += `${x === 8 ? 'M' : 'L'}${x} ${(140 - v).toFixed(1)}`;
      }
      return `<svg viewBox="0 0 ${W} 166"><path d="${beat}L312 140L8 140Z" fill="${B}26"/><path d="${beat}" fill="none" stroke="${B}" stroke-width="2"/><path d="${vox}L312 140L8 140Z" fill="${O}33"/><path d="${vox}" fill="none" stroke="${O}" stroke-width="2"/><path d="M8 140h304" stroke="${L}"/>
      ${[100, 1000, 10000].map((f) => `<path d="M${fx(f)} 140v5" stroke="${M}"/>${txt(fx(f), 158, f >= 1000 ? f / 1000 + ' kHz' : f + ' Hz', { size: 9 })}`).join('')}
      ${txt(60, 52, 'BEAT', { fill: BH, w: 700, size: 10 })}${txt(fx(2700), 52, '−2 to −3 dB', { fill: BH, size: 9.5, w: 700 })}${txt(fx(2600), 116, 'VOCAL', { fill: '#fff', w: 700, size: 10 })}</svg>`;
    },
    eqmap() { return freqSvg(-1, false); },
    serial() {
      const wave = (x0, amps, c) => amps.map((a, i) => `<rect x="${x0 + i * 6}" y="${50 - a}" width="3.600" height="${a * 2}" rx="1.800" fill="${c}"/>`).join('');
      const raw = [6, 22, 9, 30, 12, 7, 26, 10, 34, 8, 16, 5, 28, 9];
      const a = raw.map((v) => Math.min(v, 20) + Math.max(0, v - 20) * 0.3), b = a.map((v) => 12 + (v - 12) * 0.55 + 2);
      return `<svg viewBox="0 0 320 118">${wave(6, raw, M)}${wave(118, a, BH)}${wave(230, b, OH)}
      <path d="M96 50h14M208 50h14" stroke="${M}" stroke-width="1.4" stroke-linecap="round"/><path d="M107 47l3 3-3 3M219 47l3 3-3 3" fill="none" stroke="${M}" stroke-width="1.4" stroke-linecap="round"/>
      ${txt(48, 102, 'Raw take', { fill: '#eaf0ff', w: 650 })}${txt(160, 102, 'Fast: peaks caught', { fill: BH, w: 650 })}${txt(272, 102, 'Slow: smoothed', { fill: OH, w: 650 })}${txt(48, 114, 'uneven', { size: 9 })}${txt(160, 114, '3–5 dB', { size: 9 })}${txt(272, 114, '2–3 dB', { size: 9 })}</svg>`;
    },
    predelay() {
      return `<svg viewBox="0 0 320 130"><path d="M16 100h292" stroke="${L}"/><rect x="24" y="26" width="10" height="74" rx="3" fill="${O}"/>${txt(29, 18, 'dry word', { fill: OH, w: 700, size: 9.5 })}
      <path d="M96 100V54c40 0 90 30 204 44v2z" fill="${B}40" stroke="${B}" stroke-width="1.6"/>${txt(190, 50, 'reverb tail', { fill: BH, w: 700, size: 9.5 })}
      <path d="M36 112h58" stroke="${OH}"/><path d="M36 108v8M94 108v8" stroke="${OH}"/>${txt(65, 126, 'pre-delay 20–60 ms', { fill: OH, size: 9.5, w: 650 })}${txt(292, 114, 'time →', { size: 9 })}</svg>`;
    },
    pan() {
      const dot = (x, y, r, c, t, s) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${c}33" stroke="${c}" stroke-width="1.5"/>${txt(x, y + 3.5, t, { fill: '#fff', w: 700, size: s || 9 })}`;
      return `<svg viewBox="0 0 320 168"><path d="M20 150a140 140 0 0 1 280 0" fill="none" stroke="${L}"/><path d="M70 150a90 90 0 0 1 180 0" fill="none" stroke="${L}" stroke-dasharray="3 4"/><path d="M160 150V16" stroke="${L}"/>
      ${dot(160, 118, 22, O, 'LEAD', 10)}${dot(160, 66, 13, OH, 'dbl')}${dot(52, 104, 15, B, 'dbl L')}${dot(268, 104, 15, B, 'dbl R')}${dot(96, 52, 14, BH, 'harm')}${dot(224, 52, 14, BH, 'harm')}${dot(40, 46, 11, M, 'ad')}${dot(280, 46, 11, M, 'ad')}
      ${txt(22, 164, 'L', { w: 700 })}${txt(160, 164, 'CENTRE', { w: 700, size: 9 })}${txt(298, 164, 'R', { w: 700 })}${txt(160, 12, 'further back = quieter, darker, wetter', { size: 9 })}</svg>`;
    },
  };

  function freqSvg(sel, interactive) {
    const cols = [M, B, B, BH, BH, OH, O, O, OH];
    const zones = D.freq.map((z, i) => {
      const x = fx(z.lo), w = fx(z.hi) - x;
      const on = i === sel;
      const hgt = [26, 58, 72, 60, 50, 86, 64, 44, 34][i];
      return `<g ${interactive ? `data-zone="${i}"` : ''}><rect x="${x + 1}" y="10" width="${w - 2}" height="120" rx="6" fill="${on ? cols[i] + '26' : 'transparent'}"/><rect x="${x + 2}" y="${128 - hgt}" width="${w - 4}" height="${hgt}" rx="5" fill="${cols[i]}" opacity="${sel < 0 || on ? 0.9 : 0.3}"/>${txt(x + w / 2, 122 - hgt, z.name, { size: 8, fill: on || sel < 0 ? '#eaf0ff' : M, w: on ? 700 : 500 })}</g>`;
    }).join('');
    return `<svg viewBox="0 0 320 152">${zones}<path d="M8 130h304" stroke="${L}"/>${[20, 100, 1000, 10000, 20000].map((f) => txt(fx(f), 146, f >= 1000 ? f / 1000 + 'k' : f, { size: 9, a: f === 20 ? 'start' : f === 20000 ? 'end' : 'middle' })).join('')}</svg>`;
  }

  /* ---------- helpers ---------- */
  const trackDone = (t) => t.lessons.filter((l) => done.has(l.id)).length;
  const nextLesson = () => ALL.find((l) => !done.has(l.id)) || ALL[0];
  const fmtHz = (f) => (f >= 1000 ? `${f / 1000} kHz` : `${f} Hz`);

  /* ---------- views ---------- */
  const V = {
    home() {
      const total = ALL.length, n = done.size, pct = n / total, c = 2 * Math.PI * 29;
      const nx = nextLesson();
      return `<header class="hero"><div class="moon"></div><div class="eyebrow">Spectral</div><h1 class="title">From first take to finished vocal.</h1><p class="sub">A pocket guide to recording your voice properly and mixing it into a beat.</p></header>
      <button class="card progress" data-lesson="${nx.id}" style="width:100%;margin-top:24px">
        <div class="ring"><svg viewBox="0 0 68 68"><defs><linearGradient id="ringGrad"><stop stop-color="${B}"/><stop offset="1" stop-color="${O}"/></linearGradient></defs><circle class="trk" cx="34" cy="34" r="29"/><circle class="bar" cx="34" cy="34" r="29" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct)}"/></svg><b>${Math.round(pct * 100)}%</b></div>
        <div class="meta"><small>${n === 0 ? 'Start here' : n === total ? 'All lessons complete. Revisit' : 'Continue'} · ${nx.track.name}</small><strong>${nx.title}</strong></div>
        <span class="go">${svg('next')}</span></button>
      <h2 class="section-h">Two parts</h2>
      <div class="paths">${D.tracks.map((t) => `<button class="path ${t.tone}" data-tab="${t.id}">
        <svg class="art" viewBox="0 0 104 104" fill="none" stroke-linecap="round">${t.id === 'record'
          ? `<circle cx="58" cy="46" r="34" fill="${O}22"/><rect x="46" y="20" width="24" height="40" rx="12" stroke="${OH}" stroke-width="3"/><path d="M38 50a20 20 0 0 0 40 0M58 72v12M48 84h20" stroke="${OH}" stroke-width="3"/>`
          : `<circle cx="58" cy="46" r="34" fill="${B}22"/>${[40, 58, 76].map((x, i) => `<path d="M${x} 20v54" stroke="${BH}" stroke-width="3"/><rect x="${x - 7}" y="${[52, 28, 42][i]}" width="14" height="10" rx="3" fill="${BH}"/>`).join('')}`}</svg>
        <h3>${t.name}</h3><p>${t.id === 'record' ? 'Room, mic, levels and takes.' : 'EQ, compression, space and polish.'}</p>
        <div class="count">${trackDone(t)} / ${t.lessons.length} lessons</div><div class="bar-thin"><i style="width:${(trackDone(t) / t.lessons.length) * 100}%"></i></div></button>`).join('')}</div>
      <h2 class="section-h">Quick tools</h2>
      <div class="quick">${[['delay', 'clock', 'Delay times'], ['comp', 'wave', 'Compressor'], ['freq', 'tools', 'EQ map'], ['level', 'mix', 'Level check'], ['chains', 'record', 'Vocal chains'], ['lists', 'list', 'Checklists']].map(([id, ic, t]) => `<button data-tool="${id}">${svg(ic)}${t}</button>`).join('')}</div>
      <h2 class="section-h">Five rules to keep</h2>
      <div class="card rules">${D.rules.map(([b, s], i) => `<div class="rule"><div class="n">${i + 1}</div><div><b>${b}</b><span>${s}</span></div></div>`).join('')}</div>`;
    },
    track(id) {
      const t = D.tracks.find((x) => x.id === id);
      return `<div class="${t.tone}"><header><div class="eyebrow">${t.eyebrow} · ${trackDone(t)} of ${t.lessons.length} done</div><h1 class="title">${t.title}</h1><p class="sub">${t.sub}</p></header>
      <div class="rows">${t.lessons.map((l, i) => `<button class="row ${done.has(l.id) ? 'done' : ''}" data-lesson="${l.id}"><span class="num">${done.has(l.id) ? svgCheck() : i + 1}</span><span class="txt"><b>${l.title}</b><span>${l.blurb}</span></span><span class="min">${l.min} min</span></button>`).join('')}</div></div>`;
    },
    record() { return V.track('record'); },
    mix() { return V.track('mix'); },
    tools() {
      const tools = [['delay', 'Delay times'], ['comp', 'Compressor'], ['freq', 'EQ map'], ['level', 'Level check'], ['chains', 'Vocal chains'], ['lists', 'Checklists']];
      return `<header><div class="eyebrow">Tools</div><h1 class="title">Hands-on helpers</h1><p class="sub">Calculators and playgrounds for the numbers you need mid-session.</p></header>
      <div class="chips">${tools.map(([id, t]) => `<button class="chip ${state.tool === id ? 'on' : ''}" data-tool="${id}">${t}</button>`).join('')}</div>
      <div class="tool" id="tool">${T[state.tool]()}</div>`;
    },
    glossary() {
      return `<header><div class="eyebrow blue">Glossary</div><h1 class="title">Studio words, plainly</h1></header>
      <div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/></svg><input id="q" type="search" placeholder="Search ${D.glossary.length} terms" autocomplete="off" autocorrect="off" spellcheck="false"></div>
      <div class="card" style="margin-top:16px;padding:4px 16px" id="terms">${termList('')}</div>`;
    },
  };
  const svgCheck = () => `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${I.check}</svg>`;
  const termList = (q) => {
    const s = q.trim().toLowerCase();
    const hits = D.glossary.filter(([a, b]) => !s || a.toLowerCase().includes(s) || b.toLowerCase().includes(s));
    return hits.length ? hits.map(([a, b]) => `<div class="term"><b>${a}</b><p>${b}</p></div>`).join('') : `<div class="empty">No terms match “${q.replace(/[<>&]/g, '')}”.</div>`;
  };

  /* ---------- tools ---------- */
  const state = { tab: 'home', tool: store.get('tool', 'delay'), bpm: store.get('bpm', 140), comp: { thr: -20, ratio: 4, makeup: 0, inp: -8 }, zone: 5, peak: -9, chain: 'rap', taps: [] };
  const slider = (id, label, min, max, step, val, out) => `<div class="slider"><label>${label}<b id="${id}-o">${out}</b></label><input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${val}"></div>`;
  const stat = (l, v, u, cls = '', hint = '') => `<div class="stat ${cls}"><small>${l}</small><b>${v}<u>${u}</u></b>${hint ? `<em>${hint}</em>` : ''}</div>`;

  const dbfs = (p) => (p === 0 ? '0' : '−' + -p) + ' dBFS';
  const OUT = { delay: () => T._delay(), comp: () => T._comp(), level: () => T._level() };
  const T = {
    delay() {
      return `<h3>Delay &amp; reverb times</h3><p>Enter the tempo of the beat in BPM to get effect times that land on the grid.</p>
      <div class="field"><div class="bpm"><button data-bpm="-1" aria-label="Slower">−</button><input id="bpm" type="number" inputmode="numeric" min="40" max="240" value="${state.bpm}" aria-label="Tempo in BPM"><button data-bpm="1" aria-label="Faster">+</button></div><button class="tap" id="tap">Tap tempo</button></div><div id="out">${OUT.delay()}</div>`;
    },
    _delay() {
      const q = 60000 / state.bpm, ms = (x) => Math.round(q * x);
      return `<div class="list-h"><b>Delay</b></div><div class="grid2">
        ${stat('1/4 note', ms(1), 'ms', 'hot', 'Big, obvious echo. Throws.')}${stat('1/8 note', ms(0.5), 'ms', 'hot', 'The everyday vocal delay.')}
        ${stat('Dotted 1/8', ms(0.75), 'ms', '', 'Bouncy; pairs with a 1/8.')}${stat('1/8 triplet', ms(1 / 3), 'ms', '', 'For swung and trap feels.')}
        ${stat('1/16 note', ms(0.25), 'ms', '', 'Tight rhythmic thickener.')}${stat('Slapback', Math.min(120, Math.max(80, ms(0.25))), 'ms', '', 'One repeat, kept low.')}</div>
      <div class="list-h"><b>Reverb</b></div><div class="grid2">
        ${stat('Pre-delay', ms(1 / 16) < 15 ? ms(1 / 8) : ms(1 / 16), 'ms', 'cool', 'Keeps the word in front.')}${stat('Longer pre-delay', ms(1 / 8) < 25 ? ms(1 / 4) : ms(1 / 8), 'ms', 'cool', 'For slow songs and ballads.')}
        ${stat('Decay, tight', (q * 2 / 1000).toFixed(2), 's', '', 'Clears every half bar.')}${stat('Decay, lush', (q * 4 / 1000).toFixed(2), 's', '', 'Fades over one bar.')}</div>`;
    },
    comp() {
      return `<h3>Compressor playground</h3><p>Drag the controls and watch what happens to a signal coming in at the level you choose.</p><div id="out">${OUT.comp()}</div>
      ${slider('c-inp', 'Incoming level', -60, 0, 1, state.comp.inp, state.comp.inp + ' dB')}${slider('c-thr', 'Threshold', -50, 0, 1, state.comp.thr, state.comp.thr + ' dB')}${slider('c-ratio', 'Ratio', 1, 20, 0.5, state.comp.ratio, state.comp.ratio + ':1')}${slider('c-makeup', 'Makeup gain', 0, 18, 0.5, state.comp.makeup, '+' + state.comp.makeup + ' dB')}`;
    },
    _comp() {
      const c = state.comp;
      const out = (x) => (x <= c.thr ? x : c.thr + (x - c.thr) / c.ratio) + c.makeup;
      const X = (db) => 30 + ((db + 60) / 60) * 270, Y = (db) => 190 - ((Math.max(-60, Math.min(6, db)) + 60) / 66) * 180;
      const o = out(c.inp), gr = c.inp <= c.thr ? 0 : c.inp - c.thr - (c.inp - c.thr) / c.ratio;
      const grid = [-48, -36, -24, -12, 0].map((d) => `<path d="M${X(d)} ${Y(-60)}V${Y(6)}M${X(-60)} ${Y(d)}H${X(0)}" stroke="${L}" stroke-width=".7"/>${txt(X(d), 204, d, { size: 9 })}${txt(24, Y(d) + 3, d, { size: 9, a: 'end' })}`).join('');
      return `<figure class="fig" style="margin-top:14px"><svg viewBox="0 0 320 212"><rect x="${X(c.thr)}" y="${Y(6)}" width="${X(0) - X(c.thr)}" height="${Y(-60) - Y(6)}" fill="${O}14"/>${grid}
        <path d="M${X(-60)} ${Y(-60)}L${X(0)} ${Y(0)}" stroke="${M}" stroke-dasharray="3 4"/>
        <path d="M${X(-60)} ${Y(out(-60))}L${X(c.thr)} ${Y(out(c.thr))}L${X(0)} ${Y(out(0))}" fill="none" stroke="url(#cg)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        <defs><linearGradient id="cg"><stop stop-color="${B}"/><stop offset="1" stop-color="${O}"/></linearGradient></defs>
        <path d="M${X(c.thr)} ${Y(6)}V${Y(-60)}" stroke="${O}" stroke-dasharray="2 3"/>${txt(X(c.thr), Y(6) - 3 < 12 ? 12 : Y(6) - 3, 'threshold', { size: 8.5, fill: OH, a: c.thr > -14 ? 'end' : 'start' })}
        <path d="M${X(c.inp)} ${Y(-60)}V${Y(o)}H${X(-60)}" fill="none" stroke="#fff" stroke-width=".8" opacity=".5"/><circle cx="${X(c.inp)}" cy="${Y(o)}" r="6" fill="#fff" stroke="${O}" stroke-width="3"/>
        ${txt(X(-60), 204, 'in dB', { size: 8.5 })}</svg></figure>
      <div class="grid2">${stat('Signal out', (o > 0 ? '+' : '') + o.toFixed(1), 'dB', 'cool')}${stat('Gain reduction', gr ? '−' + gr.toFixed(1) : '0.0', 'dB', 'hot')}</div>
      <div class="verdict ${gr === 0 ? 'low' : gr <= 7 ? 'good' : gr <= 12 ? 'warm' : 'bad'}"><b>${gr === 0 ? 'Not compressing' : gr <= 3 ? 'Gentle levelling' : gr <= 7 ? 'Classic vocal control' : gr <= 12 ? 'Heavy. Fine for stacks' : 'Crushed'}</b>${gr === 0 ? 'The signal is under the threshold, so it passes untouched.' : gr <= 3 ? 'Smooths phrases without being heard. Good for a second compressor or a vocal bus.' : gr <= 7 ? 'The usual 3–6 dB range for a lead vocal on its loudest words.' : gr <= 12 ? 'Flat and dense. Useful on doubles and ad-libs, or blended in parallel.' : 'Expect lifeless tone, loud breaths and harsh esses unless this is a parallel copy.'}</div>`;
    },
    freq() {
      const z = D.freq[state.zone];
      return `<h3>Vocal EQ map</h3><p>Tap a range to see what lives there and what to do about it.</p>
      <figure class="fig" style="margin-top:14px" id="freqfig">${freqSvg(state.zone, true)}</figure>
      <div class="card zone-card"><div class="range">${fmtHz(z.lo)} – ${fmtHz(z.hi)}</div><h4>${z.name}</h4><p>${z.feel}</p><div class="mv"><b>Cut:</b> ${z.cut}</div><div class="mv"><b style="color:${OH}">Boost:</b> ${z.boost}</div></div>`;
    },
    level() {
      return `<h3>Recording level check</h3><p>Sing your loudest line, read the peak meter in your DAW and set it here.</p>
      ${slider('peak', 'Peak level', -48, 0, 1, state.peak, dbfs(state.peak))}<div id="out">${OUT.level()}</div>`;
    },
    _level() {
      const p = state.peak;
      const v = p >= 0 ? ['bad', 'Clipping', 'The top of the waveform is being cut off. Turn the preamp gain down and record it again; this cannot be repaired.']
        : p > -3 ? ['bad', 'Far too hot', 'One excited note and it clips. Turn the gain down by at least 6 dB.']
        : p > -6 ? ['warm', 'Risky', 'Clean so far, with no safety margin. Back the gain off a few dB.']
        : p >= -12 ? ['good', 'Right on target', 'Clean, strong and plenty of room for a louder take. Leave the knob alone.']
        : p >= -20 ? ['good', 'Safe and usable', 'Slightly conservative, and perfectly fine at 24-bit. You could add a few dB of gain.']
        : p >= -30 ? ['low', 'A little quiet', 'Still usable, though you will raise the noise when you turn it up. Add gain or move closer.']
        : ['low', 'Too quiet', 'Noise and room sound will come up with the vocal. Raise the preamp gain and sing closer to the mic.'];
      const pct = ((p + 48) / 48) * 100;
      return `<div class="card" style="margin-top:14px"><div style="display:flex;align-items:baseline;justify-content:space-between"><small style="color:var(--mute)">Loudest peak</small><b style="font:800 30px var(--display);font-variant-numeric:tabular-nums">${p === 0 ? '0' : '−' + -p}<span style="font-size:13px;color:var(--dim);margin-left:4px">dBFS</span></b></div>
      <div style="position:relative;height:16px;border-radius:8px;margin-top:12px;background:linear-gradient(90deg,${B}55 0%,${B} 50%,#7fe3b0 75%,#7fe3b0 87.500%,${O} 94%,#ff5d5d 100%)"><i style="position:absolute;top:-5px;left:calc(${pct}% - 3px);width:6px;height:26px;border-radius:3px;background:#fff;box-shadow:0 0 10px rgba(0,0,0,.6)"></i></div>
      <div style="display:flex;justify-content:space-between;font-size:10.5px;color:var(--dim);margin-top:8px;font-variant-numeric:tabular-nums"><span>−48</span><span>−36</span><span>−24</span><span>−12</span><span>0</span></div></div>
      <div class="verdict ${v[0]}"><b>${v[1]}</b>${v[2]}</div>`;
    },
    chains() {
      const c = D.chains.find((x) => x.id === state.chain);
      return `<h3>Starting vocal chains</h3><p>Plug-in order and first settings by style. Starting points to adjust by ear.</p>
      <div class="chips" style="margin-top:12px">${D.chains.map((x) => `<button class="chip ${x.id === c.id ? 'on' : ''}" data-chain="${x.id}">${x.name}</button>`).join('')}</div>
      <p style="margin-top:10px;color:#d3dcf6">${c.sub}</p><div class="chain">${c.steps.map(([b, s], i) => `<div class="step"><i>${i + 1}</i><div><b>${b}</b><span>${s}</span></div></div>`).join('')}</div>`;
    },
    lists() {
      return `<h3>Session checklists</h3><p>Tick these off as you go. Your progress is saved on this device.</p>
      ${D.checklists.map((l) => { const n = l.items.filter((_, i) => checks[l.id + i]).length; return `<div class="list-h"><b>${l.name}</b><small>${n} / ${l.items.length}</small></div><div class="card" style="padding:4px 14px">${l.items.map((t, i) => `<button class="check ${checks[l.id + i] ? 'on' : ''}" data-check="${l.id + i}"><span class="box"><svg viewBox="0 0 24 24">${I.check}</svg></span><span>${t}</span></button>`).join('')}</div>`; }).join('')}
      <button class="reset" id="reset">Clear all checklists</button>`;
    },
  };

  /* ---------- rendering ---------- */
  const TABS = [['home', 'Home'], ['record', 'Record'], ['mix', 'Mix'], ['tools', 'Tools'], ['glossary', 'Glossary']];
  function renderTabs() {
    tabsEl.innerHTML = TABS.map(([id, t]) => `<button class="tab ${state.tab === id ? 'on' : ''}" data-tab="${id}" aria-current="${state.tab === id ? 'page' : 'false'}">${svg(id)}<span>${t}</span></button>`).join('');
  }
  function render(keepScroll) {
    const y = view.scrollTop;
    view.innerHTML = V[state.tab]();
    view.className = keepScroll ? '' : 'fade-in';
    view.scrollTop = keepScroll ? y : 0;
    renderTabs();
  }
  function go(tab) { if (tab !== state.tab) haptic(); state.tab = tab; render(false); }
  function renderTool() {
    const el = $('#tool'); if (!el) return;
    el.innerHTML = T[state.tool]();
  }
  function openTool(id) {
    state.tool = id; store.set('tool', id); haptic();
    if (state.tab !== 'tools') { state.tab = 'tools'; render(false); }
    else { $$('.chip[data-tool]', view).forEach((c) => c.classList.toggle('on', c.dataset.tool === id)); renderTool(); }
    const on = $('.chip[data-tool].on', view); if (on) { const c = on.parentNode; c.scrollLeft = on.offsetLeft - (c.clientWidth - on.offsetWidth) / 2; }
  }

  /* ---------- lesson ---------- */
  let current = null;
  function openLesson(id) {
    const l = ALL.find((x) => x.id === id); if (!l) return;
    current = l; haptic();
    const idx = ALL.indexOf(l), nx = ALL[idx + 1], pos = l.track.lessons.findIndex((x) => x.id === id) + 1;
    lessonEl.className = l.track.tone + ' open';
    lessonEl.setAttribute('aria-hidden', 'false');
    lessonEl.innerHTML = `<div class="lesson-bar"><button id="back" aria-label="Back">${svg('back')}</button><span>${l.track.name} · ${pos} of ${l.track.lessons.length}</span><i class="readbar"></i></div>
      <div class="lesson-scroll"><div class="eyebrow">${l.min} min read</div><h1 class="title">${l.title}</h1><p class="lede">${l.lede}</p><div class="body">${l.body.join('')}</div>
      <div class="cta"><button class="btn ${done.has(id) ? 'done' : ''}" id="mark">${done.has(id) ? svgCheck() + 'Completed' : 'Mark as complete'}</button>${nx ? `<button class="btn ghost" data-lesson="${nx.id}">Next: ${nx.title}</button>` : ''}</div></div>`;
    $$('[data-fig]', lessonEl).forEach((f) => f.insertAdjacentHTML('afterbegin', FIG[f.dataset.fig]()));
    const sc = $('.lesson-scroll', lessonEl), bar = $('.readbar', lessonEl);
    sc.addEventListener('scroll', () => { bar.style.width = Math.min(100, (sc.scrollTop / Math.max(1, sc.scrollHeight - sc.clientHeight)) * 100) + '%'; }, { passive: true });
  }
  function closeLesson() {
    lessonEl.classList.remove('open'); lessonEl.setAttribute('aria-hidden', 'true'); current = null;
    render(true);
  }

  /* ---------- events ---------- */
  document.addEventListener('click', (e) => {
    const t = e.target.closest('button, [data-zone]'); if (!t) return;
    const d = t.dataset;
    if (t.id === 'back') return closeLesson();
    if (t.id === 'mark') {
      const id = current.id;
      if (done.has(id)) done.delete(id); else { done.add(id); haptic('success'); }
      store.set('done', [...done]);
      t.className = 'btn ' + (done.has(id) ? 'done' : '');
      t.innerHTML = done.has(id) ? svgCheck() + 'Completed' : 'Mark as complete';
      return;
    }
    if (d.lesson) return openLesson(d.lesson);
    if (d.tool) return openTool(d.tool);
    if (d.tab) { if (current) closeLesson(); return go(d.tab); }
    if (d.chain) { state.chain = d.chain; haptic(); return renderTool(); }
    if (d.zone) { state.zone = +d.zone; haptic(); return renderTool(); }
    if (d.bpm) { setBpm(state.bpm + +d.bpm); haptic(); $('#bpm').value = state.bpm; return refresh(); }
    if (d.check) {
      checks[d.check] = !checks[d.check]; store.set('checks', checks); haptic(checks[d.check] ? 'medium' : 'light');
      return renderTool();
    }
    if (t.id === 'reset') { Object.keys(checks).forEach((k) => delete checks[k]); store.set('checks', checks); return renderTool(); }
    if (t.id === 'tap') {
      const now = performance.now();
      state.taps = state.taps.filter((x) => now - x < 2500).concat(now).slice(-6);
      haptic();
      if (state.taps.length > 1) { const gaps = state.taps.slice(1).map((x, i) => x - state.taps[i]); setBpm(Math.round(60000 / (gaps.reduce((a, b) => a + b) / gaps.length))); $('#bpm').value = state.bpm; refresh(); }
    }
  });
  function setBpm(v) { state.bpm = Math.max(40, Math.min(240, Math.round(v) || 120)); store.set('bpm', state.bpm); }

  const refresh = () => { const o = $('#out'); if (o && OUT[state.tool]) o.innerHTML = OUT[state.tool](); };
  const FMT = { 'c-inp': (v) => v + ' dB', 'c-thr': (v) => v + ' dB', 'c-ratio': (v) => v + ':1', 'c-makeup': (v) => '+' + v + ' dB', peak: dbfs };
  document.addEventListener('input', (e) => {
    const t = e.target;
    if (t.id === 'q') { $('#terms').innerHTML = termList(t.value); return; }
    if (t.id === 'bpm') { const v = +t.value; if (v >= 40 && v <= 240) { setBpm(v); refresh(); } return; }
    if (t.type !== 'range') return;
    const v = +t.value;
    if (t.id === 'peak') state.peak = v; else state.comp[t.id.slice(2)] = v;
    $('#' + t.id + '-o').textContent = FMT[t.id](v);
    refresh();
  });
  document.addEventListener('change', (e) => { if (e.target.id === 'bpm') { setBpm(+e.target.value); e.target.value = state.bpm; refresh(); } });

  /* swipe from the left edge to close a lesson */
  let sx = null, sy = 0;
  lessonEl.addEventListener('touchstart', (e) => { const t = e.touches[0]; sx = t.clientX < 28 ? t.clientX : null; sy = t.clientY; }, { passive: true });
  lessonEl.addEventListener('touchend', (e) => { if (sx === null) return; const t = e.changedTouches[0]; if (t.clientX - sx > 70 && Math.abs(t.clientY - sy) < 60) closeLesson(); sx = null; }, { passive: true });

  render(false);
})();
