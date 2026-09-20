/* Segmentation UI. Plans are previewed on the server before an atomic commit. */
const CHUNK_LABELS = {
  default: 'Default · keep existing segments',
  duration: 'Target duration',
  sentence: 'Sentence endings',
  pause: 'Speech pauses / end of speech',
  sentence_pause: 'Sentence endings or speech pauses'
};

function chunkImportMarkup() {
  return `<section class="card chunk-import">
    <div><h2>Chunking</h2><p>Choose how your recording is divided into reviewable pieces.</p></div>
    <div class="chunk-fields">
      <label>Mode<select id="import-chunk-mode">${Object.entries(CHUNK_LABELS).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></label>
      <label id="import-duration-field" hidden>Target duration (seconds)<input id="import-chunk-seconds" type="number" min="1" max="600" value="10" step="1"></label>
      <label id="import-pause-field" hidden>Minimum pause (seconds)<input id="import-pause-seconds" type="number" min="0.2" max="5" value="0.6" step="0.1"></label>
    </div>
    <p id="import-chunk-description">Default keeps supplied transcript cues or Whisper segments. Manual splits and merges are available in Review.</p>
  </section>`;
}

function bindChunkImport() {
  const mode = $('#import-chunk-mode');
  if (!mode) return;
  mode.value = state.chunkMode || 'default';
  $('#import-chunk-seconds').value = state.chunkSeconds || 10;
  $('#import-pause-seconds').value = state.pauseSeconds || .6;
  function changed() {
    state.chunkMode = mode.value;
    $('#import-duration-field').hidden = mode.value !== 'duration';
    $('#import-pause-field').hidden = !['pause','sentence_pause'].includes(mode.value);
    $('#import-chunk-description').textContent = mode.value === 'default'
      ? 'Default keeps supplied transcript cues or Whisper segments. Manual splits and merges are available in Review.'
      : 'Text stays unchanged and existing cue boundaries stay in place. Estimated text/timing assignments are flagged. Pause detection does not identify different speakers.';
  }
  mode.onchange = changed;
  $('#import-chunk-seconds').oninput = e => state.chunkSeconds = Number(e.target.value);
  $('#import-pause-seconds').oninput = e => state.pauseSeconds = Number(e.target.value);
  changed();
}

function mountChunkControls() {
  const timing = $('.timing-card');
  if (!timing || $('#chunk-controls')) return;
  timing.insertAdjacentHTML('beforebegin', `<section id="chunk-controls" class="card chunk-controls">
    <div><h2>Chunking</h2><small>Preview changes · undo at any time</small></div>
    <div class="chunk-buttons">
      <button class="button" id="auto-chunk">${icon('settings')} Auto chunk…</button>
      <button class="button" id="manual-split">${icon('edit')} Split…</button>
      <button class="button" id="manual-merge">${icon('compare')} Merge next…</button>
    </div>
  </section>`);
  $('#auto-chunk').onclick = () => showChunkDialog('automatic');
  $('#manual-split').onclick = () => showChunkDialog('split');
  $('#manual-merge').onclick = () => showChunkDialog('merge');
}

function originalForSegment(segment, project) {
  const ids = segment.source_ids || [segment.id];
  const originals = ids.map(id => project.original_segments.find(s => s.id === id)).filter(Boolean);
  return {text: originals.map(s => s.text).join('\n'), start: originals[0]?.start ?? segment.start,
          end: originals.at(-1)?.end ?? segment.end, ids};
}

async function showChunkDialog(kind) {
  if (mutationPromise) await mutationPromise;
  const editor = $('#transcript-editor');
  const cursor = editor ? [...editor.value.slice(0, editor.selectionStart)].length : 0;
  try { await flushText(); } catch { return; }
  audio.pause();
  const project = state.project, segment = selected(), revision = project.revision;
  const codepoints = [...segment.text];
  const hasCursor = cursor > 0 && cursor < codepoints.length;
  let defaultOffset = hasCursor ? cursor : Math.floor(codepoints.length / 2);
  if (!hasCursor) {
    const spaces = codepoints.map((c,i) => /\s/.test(c) ? i + 1 : null).filter(i => i !== null && i < codepoints.length);
    if (spaces.length) defaultOffset = spaces.reduce((a,b) => Math.abs(b-defaultOffset) < Math.abs(a-defaultOffset) ? b : a);
  }
  const initialTime = audio.currentTime > segment.start && audio.currentTime < segment.end
    ? audio.currentTime : (segment.start + segment.end) / 2;
  const modeFields = kind === 'automatic' ? `<div class="chunk-fields">
      <label>Mode<select id="chunk-mode">${Object.entries(CHUNK_LABELS).map(([key,label])=>`<option value="${key}" ${key==='sentence'?'selected':''}>${label}</option>`).join('')}</select></label>
      <label>Apply to<select id="chunk-scope"><option value="selected">Selected segment</option><option value="all">Whole transcript</option></select></label>
      <label id="duration-field" hidden>Target duration (seconds)<input id="chunk-seconds" type="number" min="1" max="600" value="10"></label>
      <label id="pause-field" hidden>Minimum pause (seconds)<input id="chunk-pause" type="number" min="0.2" max="5" step="0.1" value="0.6"></label>
    </div><p>Default keeps current segments. Other modes split within existing cues and preserve gaps. Sentence timings use word timestamps when available; estimates are flagged. Speech pauses do not identify a change of person.</p>`
    : kind === 'split' ? `<div class="chunk-fields">
      <label>Split audio at<input id="split-time" type="text" value="${fmt(initialTime,true)}"></label>
      <label>Boundary type<select id="boundary-kind"><option value="manual">Manual boundary</option><option value="speaker_turn">End of speaker / speaker turn (manual)</option></select></label>
      <label>Text split after character<input id="split-offset" type="number" min="1" max="${Math.max(1,codepoints.length-1)}" value="${defaultOffset}"></label>
    </div><p>Choose an audio time and click between words below to place the text split. Both portions are preserved exactly.</p>
    <textarea id="split-text" class="split-text" readonly aria-label="Place text split cursor">${esc(segment.text)}</textarea>
    <div id="split-portions" class="split-portions"></div>`
    : `<p>Combine segment <strong>${esc(segment.id)}</strong> with the next segment. Both texts are preserved with a newline between them. The merged audio spans both segments and any gap; the preview shows the result.</p>`;
  showDialog(`<h2>${kind==='automatic'?'Automatic chunking':kind==='split'?'Split segment':'Merge with next segment'}</h2>
    <p>Saved revision ${revision} · segment ${esc(segment.id)} · ${fmt(segment.start,true)} – ${fmt(segment.end,true)}</p>
    ${modeFields}<button class="button primary" id="preview-chunks">Preview chunks</button>
    <div id="chunk-feedback" aria-live="polite"></div>`);
  let generation = 0;
  function invalidate() { generation++; $('#chunk-feedback').innerHTML=''; }
  $$('#dialog-content input, #dialog-content select').forEach(el => el.addEventListener('input', invalidate));
  if (kind === 'automatic') {
    $('#chunk-mode').onchange = () => {
      const mode = $('#chunk-mode').value;
      $('#duration-field').hidden = mode !== 'duration';
      $('#pause-field').hidden = !['pause','sentence_pause'].includes(mode);
    };
  }
  if (kind === 'split') {
    function portions() {
      const n = Number($('#split-offset').value);
      $('#split-portions').innerHTML = `<div><b>First chunk</b><p>${esc(codepoints.slice(0,n).join(''))}</p></div><div><b>Second chunk</b><p>${esc(codepoints.slice(n).join(''))}</p></div>`;
    }
    const text = $('#split-text');
    function fromCursor() {
      $('#split-offset').value = [...text.value.slice(0,text.selectionStart)].length;
      invalidate(); portions();
    }
    text.onclick = fromCursor; text.onkeyup = fromCursor;
    $('#split-offset').addEventListener('input', portions);
    portions();
  }
  $('#preview-chunks').onclick = async () => {
    let opts;
    try {
      opts = {segment_id:segment.id, scope:'selected', mode:kind};
      if (kind === 'automatic') opts = {...opts, mode:$('#chunk-mode').value, scope:$('#chunk-scope').value,
        seconds:Number($('#chunk-seconds').value), pause_seconds:Number($('#chunk-pause').value)};
      if (kind === 'split') opts = {...opts, time:parseTime($('#split-time').value),
        text_offset:Number($('#split-offset').value), boundary_kind:$('#boundary-kind').value};
    } catch(error) { toast(error.message,true); return; }
    const current = ++generation;
    const stillOpen = () => $('#dialog').open && $('#preview-chunks') && generation === current;
    const button = $('#preview-chunks'); button.disabled = true;
    $('#chunk-feedback').innerHTML='<p class="processing">Preparing preview…</p>';
    try {
      let job = await api(`/api/projects/${project.id}/chunking/preview`,jsonOptions('POST',{revision,options:opts}));
      while (job.status === 'processing' && stillOpen()) {
        await new Promise(resolve=>setTimeout(resolve,350));
        job = await api(`/api/jobs/${job.id}`);
      }
      if (!stillOpen()) return;
      if (job.status === 'failed') throw Error(job.message);
      const preview = job.preview;
      $('#chunk-feedback').innerHTML = `<div class="chunk-preview">
        <h3>${preview.before_count} → ${preview.after_count} total chunks</h3>
        ${preview.warnings.map(w=>`<div class="note">${icon('info')}<span>${esc(w)}</span></div>`).join('')}
        ${!preview.changed_count?'<p>No boundaries need changing with these settings.</p>':`
        <div class="chunk-preview-rows">${preview.segments.map(s=>`<div class="chunk-preview-row"><small>${esc(s.id)} · ${fmt(s.start,true)} → ${fmt(s.end,true)} · ${esc(s.status)}</small><p>${esc(s.text)}</p></div>`).join('')}</div>
        <p>${preview.changed_count} records affected. Showing up to 100 resulting changed chunks. Changes save together and can be undone.</p>
        <button class="button primary" id="apply-chunks">Apply chunking</button>`}
      </div>`;
      if ($('#apply-chunks')) $('#apply-chunks').onclick = async () => {
        if (mutationPromise || state.busy) return;
        $('#apply-chunks').disabled = true;
        state.busy = true;
        mutationPromise = (async () => {
          try {
            const result = await api(`/api/projects/${project.id}/chunking/apply`, jsonOptions('POST', {revision,proposal_id:preview.proposal_id}));
            state.project=result;
            state.selected=Math.max(0,result.segments.findIndex(s=>s.id===segment.id));
            state.limit=selected().end;
            $('#dialog').close();
            renderReview(); await refreshAudit();
            toast(`Saved ${result.segments.length} chunks. Undo restores the previous structure.`);
          } catch(error) {
            const feedback = $('#chunk-feedback');
            if (feedback) feedback.insertAdjacentHTML('beforeend',`<div class="error-box">${esc(error.message)}</div>`);
            else toast(error.message, true);
            if ($('#apply-chunks')) $('#apply-chunks').disabled=false;
          } finally {state.busy=false;}
        })().finally(()=>mutationPromise=null);
        await mutationPromise;
      };
    } catch(error) {
      if (stillOpen()) $('#chunk-feedback').innerHTML=`<div class="error-box">${esc(error.message)}</div>`;
    } finally { if ($('#preview-chunks')) $('#preview-chunks').disabled=false; }
  };
}
