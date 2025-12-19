document.addEventListener('DOMContentLoaded', function () {
  // Simple authentication: prompt for user ID if not set
  function getUserId() {
    let userId = localStorage.getItem('user_id');
    if (!userId) {
      userId = prompt('Enter your user ID (for demo, any string):');
      if (userId) localStorage.setItem('user_id', userId);
    }
    return userId;
  }
  const USER_ID = getUserId();
  const form = document.getElementById('track-form');
  const invInput = document.getElementById('tracking-number');
  const resultDiv = document.getElementById('result');

  // User dropdown logic
  const userDropdownList = document.getElementById('user-dropdown-list');
  const addNewUserItem = document.getElementById('add-new-user');
  // Maintain a list of recent user IDs in localStorage
  function getRecentUserIds() {
    let ids = [];
    try {
      ids = JSON.parse(localStorage.getItem('recent_user_ids') || '[]');
    } catch {}
    return Array.isArray(ids) ? ids : [];
  }
  function setRecentUserIds(ids) {
    localStorage.setItem('recent_user_ids', JSON.stringify(ids.slice(0, 6)));
  }
  function addRecentUserId(id) {
    let ids = getRecentUserIds();
    ids = [id, ...ids.filter(x => x !== id)];
    setRecentUserIds(ids);
  }
  addRecentUserId(USER_ID);

  function renderUserDropdown() {
    if (!userDropdownList) return;
    // Remove all except the last item (add/change)
    while (userDropdownList.children.length > 1) {
      userDropdownList.removeChild(userDropdownList.firstChild);
    }
    const ids = getRecentUserIds();
    ids.forEach(id => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.className = 'dropdown-item';
      a.href = '#';
      a.textContent = id === USER_ID ? id + ' (current)' : id;
      if (id === USER_ID) a.style.fontWeight = 'bold';
      a.addEventListener('click', function(e) {
        e.preventDefault();
        if (id !== USER_ID) {
          localStorage.setItem('user_id', id);
          location.reload();
        }
      });
      li.appendChild(a);
      userDropdownList.insertBefore(li, userDropdownList.lastElementChild);
    });
  }
  renderUserDropdown();
  if (addNewUserItem) {
    addNewUserItem.addEventListener('click', function(e) {
      e.preventDefault();
      const newUserId = prompt('Enter a new user ID:');
      if (newUserId) {
        localStorage.setItem('user_id', newUserId);
        addRecentUserId(newUserId);
        location.reload();
      }
    });
  }

  // map courier name (human) to a small image file key
  function courierKey(name) {
    if (!name) return 'unknown';
    name = name.toLowerCase();
    if (name.indexOf('cj') !== -1) return 'cj';
    if (name.indexOf('cvsnet') !== -1 || name.indexOf('gs') !== -1 || name.indexOf('cvs') !== -1) return 'cvs';
    if (name.indexOf('lotte') !== -1 || name.indexOf('롯데') !== -1 )return 'lotte';
    if (name.indexOf('7-11') !== -1 || name.indexOf('7-eleven') !== -1 )return '7-eleven';
    if (name.indexOf('hanjin') !== -1) return 'hanjin';
    if (name.indexOf('cu') !== -1 || name.indexOf('cupost') !== -1) return 'cupost';
    if (name.indexOf('post') !== -1 || name.indexOf('korea') !== -1) return 'koreapost';
    
    return 'unknown';
  }

  // status keywords (will be fetched from server to keep in sync)
  let STATUS_KEYWORDS = {
    delivered: ['delivered','배송완료','배달완료','배달 완료','배송 완료','수령','고객에게 전달','수령완료'],
    error: ['error','not found','notfound','fail','failed','조회불가','unavailable','오류','실패','등록되지','검색 불가','존재하지 않음','없음']
  };

  function showLoading() {
    resultDiv.innerHTML = `
      <div class="card">
        <div class="card-body">
          <span class="spinner-border spinner" role="status" aria-hidden="true"></span>
          <span class="ms-2">Searching...</span>
        </div>
      </div>`;
  }

  function showError(msg, details) {
    resultDiv.innerHTML = `
      <div class="card border-danger">
        <div class="card-body text-danger">
          <h5 class="card-title">Error</h5>
          <p class="card-text">${msg}</p>
          ${details ? `<pre class="result-json">${JSON.stringify(details, null, 2)}</pre>` : ''}
        </div>
      </div>`;
  }

  function renderResult(data) {
    if (data.error) {
      showError(data.error, data);
      return;
    }

    const latest = data.latest_event || {};
    const history = Array.isArray(data.history) ? data.history : [];

    const logo = courierKey(data.courier || '');

    let html = `
      <div class="card">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <h5 class="card-title mb-1"><img src="/static/img/${logo}.svg" class="courier-logo" alt="${data.courier || 'Courier'}">${data.courier || 'Unknown'}</h5>
              <p class="mb-1"><strong>Tracking:</strong> ${data.tracking_number || ''}</p>
              <p class="note mb-0"><strong>Status:</strong> ${data.status || 'Unknown'}${typeof data.days_taken === 'number' ? ` <span class='badge bg-info text-dark ms-2'>${data.days_taken} day${data.days_taken === 1 ? '' : 's'}</span>` : ''}</p>
            </div>
            <div class="text-end">
              ${latest.time ? `<small class="text-muted">Latest: ${latest.time}</small>` : ''}
            </div>
          </div>
        </div>
      </div>`;

    if (history.length) {
      html += `
        <div class="card">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">History</h6>
            <div class="table-responsive">
              <table class="table table-sm history-table">
                <thead>
                  <tr><th>Time</th><th>Location</th><th>Message</th></tr>
                </thead>
                <tbody>
                  ${history.map(h => `
                    <tr>
                      <td>${h.time || ''}</td>
                      <td>${h.location || ''}</td>
                      <td>${h.message || ''}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>`;
    } else {
      html += `
        <div class="card">
          <div class="card-body">
            <p class="note mb-0">No history available for this tracking number.</p>
            <pre class="result-json mt-2">${JSON.stringify(data, null, 2)}</pre>
          </div>
        </div>`;
    }

    // Inline add-to-watchlist controls (label + add button)
    html += `
      <div class="mt-3 d-flex gap-2 align-items-center">
        <input class="form-control form-control-sm add-inline-label" placeholder="Label (optional)" aria-label="Label for watchlist" />
        <button class="btn btn-success btn-sm btn-add-inline" data-tracking="${data.tracking_number || ''}">+ Add to watchlist</button>
      </div>`;

    resultDiv.innerHTML = html;

    // Attach handler for the inline add button
    const addBtn = resultDiv.querySelector('.btn-add-inline');
    if (addBtn) {
      addBtn.addEventListener('click', async (e)=>{
        e.preventDefault();
        const tracking = addBtn.getAttribute('data-tracking');
        const labelEl = resultDiv.querySelector('.add-inline-label');
        const label = labelEl ? (labelEl.value || '').trim() : '';
        try {
          const r = await fetch('/api/tracked', { method: 'POST', headers: {'Content-Type':'application/json', 'X-User-Id': USER_ID}, body: JSON.stringify({ tracking: tracking, label: label }) });
          const d = await r.json().catch(()=>({}));
          if (r.status === 200 || r.status === 201) {
            showAddMessage('Added to watchlist', 'success');
            renderTrackedList();
            // highlight the newly added item when it appears
            setTimeout(()=>{
              try {
                const card = document.querySelector(`#tracked-list .card[data-id='${d.id}']`);
                if (card) {
                  card.classList.add('added-highlight');
                  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  setTimeout(()=> card.classList.remove('added-highlight'), 1800);
                }
              } catch (err) { console.error('highlight failed', err); }
            }, 400);
          } else if (r.status === 409) {
            showAddMessage('Already tracked', 'warning');
          } else {
            showAddMessage('Error adding: '+(d.error || r.statusText), 'danger');
          }
        } catch (err) {
          console.error('Add inline failed', err);
          showAddMessage('Network error while adding', 'danger');
        }
      });
    }
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const inv = invInput.value.trim();
    if (!inv) return;

    showLoading();

    try {
      const resp = await fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracking_number: inv })
      });

      const data = await resp.json();
      if (!resp.ok) {
        showError(data.error || resp.statusText, data);
        return;
      }

      renderResult(data);
    } catch (err) {
      showError('Request failed', { message: err.message });
    }
  });

  // clear button for the top tracking input
  const clearBtn = document.getElementById('clear-tracking');
  const invField = document.getElementById('tracking-number');
  if (clearBtn && invField) {
    clearBtn.addEventListener('click', (e)=>{ e.preventDefault(); invField.value = ''; invField.focus(); });
    // small UX: pressing Escape clears the field
    invField.addEventListener('keydown', (e)=>{ if (e.key === 'Escape') { invField.value = ''; } });
  }

  // The update button is rendered alongside the tracked-controls and
  // attached when those controls are created (see renderTrackedList()).
  // We intentionally do not capture the button reference at top-level
  // since it is created dynamically; instead we query it inside
  // renderTrackedList() and attach the handler once.

  // --- Tracked list UI ---
  async function renderTrackedList() {
    // Read UI controls for sorting/filtering
    let sortVal = document.getElementById('sort-select') ? document.getElementById('sort-select').value : '';
    // Default to 'first_event:desc' (newest-first) on initial load when no explicit sort is set
    if (!sortVal) sortVal = 'first_event:desc';
    const statusFilter = document.getElementById('status-filter') ? document.getElementById('status-filter').value : '';
    let url = '/api/tracked';
    const q = [];
    if (sortVal) {
      const [sortField, order] = sortVal.split(':');
      q.push(`sort=${encodeURIComponent(sortField)}`);
      q.push(`order=${encodeURIComponent(order)}`);
    }
    if (statusFilter) q.push(`status=${encodeURIComponent(statusFilter)}`);
    const searchEl = document.getElementById('tracked-search');
    const searchVal = searchEl ? (searchEl.value || '').trim() : '';
    if (searchVal) q.push(`q=${encodeURIComponent(searchVal)}`);
    if (q.length) url += '?' + q.join('&');

    const r = await fetch(url, { cache: 'no-store', headers: { 'X-User-Id': USER_ID } });
    const data = await r.json();
    const items = data.items || [];
    // no header badge — nothing to update; wrapper will show items

    // ensure container exists
    let wrapper = document.getElementById('tracked-wrapper');
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.id = 'tracked-wrapper';
      wrapper.innerHTML = `<h3 class="mt-4">Tracked numbers</h3><div class="tracked-controls mt-1 mb-2"></div><div id="tracked-list"></div>`;
      resultDiv.parentNode.insertBefore(wrapper, resultDiv.nextSibling);

      // populate the small controls area under the title (compact)
      const ctrl = wrapper.querySelector('.tracked-controls');
      ctrl.innerHTML = `
        <div class="d-flex gap-2 align-items-center">
          <input id="tracked-search" class="form-control form-control-sm" placeholder="Search tracking, label, status..." style="width:220px;" />
          <select id="sort-select" class="form-select form-select-sm w-auto">
            <option value="first_event:desc">First event (newest)</option>
            <option value="first_event:asc">First event (oldest)</option>
            <option value="created_at:desc">Registered (newest)</option>
            <option value="created_at:asc">Registered (oldest)</option>
            <option value="last_checked:desc">Last checked (newest)</option>
            <option value="last_checked:asc">Last checked (oldest)</option>
          </select>
            <select id="status-filter" class="form-select form-select-sm w-auto">
            <option value="">All statuses</option>
            <option value="delivered">Delivered</option>
            <option value="error">Error</option>
            <option value="other">Other</option>
          </select>
            <div class="tracked-update-wrapper">
              <button id="update-all-btn" class="btn btn-outline-primary btn-sm">Update</button>
            </div>
        </div>`;

      // attach listeners for these controls
      const ss = document.getElementById('sort-select');
      // reflect the effective sort in the UI control
      if (ss) ss.value = sortVal;
      const sf = document.getElementById('status-filter');
      const searchEl = document.getElementById('tracked-search');
      if (ss) ss.addEventListener('change', renderTrackedList);
      if (sf) sf.addEventListener('change', renderTrackedList);
      // debounce search input
      function debounce(fn, ms){ let t = null; return (...args)=>{ if (t) clearTimeout(t); t = setTimeout(()=> fn(...args), ms); }; }
      if (searchEl) {
        searchEl.addEventListener('input', debounce(renderTrackedList, 250));
        // prevent parent click handlers from stealing focus when clicking here
        searchEl.addEventListener('mousedown', (e)=> e.stopPropagation());
        searchEl.addEventListener('click', (e)=> e.stopPropagation());
        searchEl.addEventListener('keydown', (e)=> e.stopPropagation());
        // be explicit about being interactive
        searchEl.style.pointerEvents = 'auto';
        searchEl.tabIndex = 0;
      }
        // Ensure the update button is bound once (re-query since element is just rendered)
        const updateBtnNow = document.getElementById('update-all-btn');
        if (updateBtnNow && !updateBtnNow.dataset.bound) {
          updateBtnNow.dataset.bound = '1';
          updateBtnNow.addEventListener('click', async (e)=>{
            e.preventDefault();
            updateBtnNow.disabled = true;
            const origText = updateBtnNow.innerText;
            updateBtnNow.innerText = 'Updating...';
            try {
              // Concurrently update only cards that are not delivered/completed
              const cards = Array.from(document.querySelectorAll('#tracked-list .card'));
              let updatedCount = 0;
              // Show spinner for all cards to be updated
              const toUpdate = cards.filter(card => {
                // Check if card has delivered/completed status
                return !card.classList.contains('status-delivered');
              });
              for (const card of toUpdate) {
                card.classList.add('checking');
                if (!card.querySelector('.spinner-overlay')) {
                  const overlay = document.createElement('div');
                  overlay.className = 'spinner-overlay';
                  overlay.innerHTML = '<span class="spinner-border text-primary" role="status" aria-hidden="true"></span>';
                  card.appendChild(overlay);
                }
              }
              // Fire all update requests in parallel for non-delivered
              await Promise.all(toUpdate.map(async (card) => {
                const id = card.getAttribute('data-id');
                try {
                  const r = await fetch(`/api/tracked/${id}/check`, { method: 'POST', cache: 'no-store', headers: { 'X-User-Id': USER_ID } });
                  const data = await r.json().catch(()=>({}));
                  // update last-checked small text
                  const small = card.querySelector('small.text-muted');
                  if (small) small.innerText = 'last checked ' + (data.result && data.result.latest_event && data.result.latest_event.time ? data.result.latest_event.time : new Date().toISOString().slice(0,19).replace('T',' '));
                  // update status area (note) with courier/status if available
                  const res = data.result || {};
                  const note = card.querySelector('.note');
                  if (note) {
                    const courier = res.courier || '';
                    const status = res.status || res.error || '';
                    const logo = courier ? courierKey(courier) : 'unknown';
                    note.innerHTML = courier ? `<img src="/static/img/${logo}.svg" class="courier-logo-sm" alt="${courier}"> ${courier} — ${status}` : (status || '');
                  }
                  // update card color class based on status
                  const lastStatus = (res.status || res.error || '').toLowerCase();
                  ['status-delivered','status-error','status-other'].forEach(c => card.classList.remove(c));
                  if (statusClassFor(lastStatus) === 'status-delivered') card.classList.add('status-delivered');
                  else if (statusClassFor(lastStatus) === 'status-error') card.classList.add('status-error');
                  else card.classList.add('status-other');
                  // remove spinner overlay and checking state for this card
                  const ov = card.querySelector('.spinner-overlay');
                  if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
                  card.classList.remove('checking');
                  // success flash or error flash
                  if (res && res.error) {
                    card.style.transition = 'background-color .2s ease';
                    card.style.backgroundColor = 'rgba(220,53,69,0.08)';
                    setTimeout(()=> card.style.backgroundColor = '', 1200);
                  } else {
                    card.classList.add('checked-success');
                    setTimeout(()=> card.classList.remove('checked-success'), 1000);
                  }
                  updatedCount++;
                } catch (err) {
                  // error flash (red)
                  card.style.transition = 'background-color .2s ease';
                  card.style.backgroundColor = 'rgba(220,53,69,0.08)';
                  setTimeout(()=> card.style.backgroundColor = '', 1200);
                  const ov = card.querySelector('.spinner-overlay');
                  if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
                  card.classList.remove('checking');
                }
              }));
              showAddMessage(`Updated ${updatedCount} item${updatedCount===1?'':'s'}`, 'success');
              renderTrackedList();
            } catch (err) {
              console.error('Update all failed', err);
              showAddMessage('Network error while updating', 'danger');
            } finally {
              updateBtnNow.disabled = false;
              updateBtnNow.innerText = origText;
            }
          });
        }
    }

    const trackedListDiv = document.getElementById('tracked-list');
    if (!items.length) {
      trackedListDiv.innerHTML = '<div class="card mt-3"><div class="card-body"><p class="note mb-0">No tracked numbers yet.</p></div></div>';
      return;
    }

    // helper: convert status string to a CSS class for coloring
    function statusClassFor(status) {
      if (!status) return 'status-other';
      const s = String(status).toLowerCase();
      for (const k of (STATUS_KEYWORDS.delivered || [])) if (s.indexOf(k) !== -1) return 'status-delivered';
      for (const k of (STATUS_KEYWORDS.error || [])) if (s.indexOf(k) !== -1) return 'status-error';
      return 'status-other';
    }

    function detailsFor(last) {
      if (!last) return '';
      const latest = last.latest_event || {};
      const history = Array.isArray(last.history) ? last.history : [];
      let html = `<div class="tracked-details">
          <div><strong>Status:</strong> ${last.status || ''}</div>
          ${latest.time || latest.message ? `<div class="mt-1"><small class="text-muted">Latest: ${latest.time || ''} ${latest.message || ''}</small></div>` : ''}`;

      if (history.length) {
        html += `
          <div class="table-responsive mt-2">
            <table class="table table-sm history-table mb-0">
              <thead><tr><th>Time</th><th>Location</th><th>Message</th></tr></thead>
              <tbody>
                ${history.map(h => `
                  <tr>
                    <td>${h.time || ''}</td>
                    <td>${h.location || ''}</td>
                    <td>${h.message || ''}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>`;
      } else if (last._debug && last._debug.snippet) {
        html += `<details class="mt-2"><summary>Raw debug snippet</summary><pre class="result-json">${last._debug.snippet}</pre></details>`;
      }

      html += `</div>`;
      return html;
    }


    // Format timestamp as YYYY-MM-DD HH:mm (or fallback to original)
    function formatTimestamp(ts) {
      if (!ts) return '';
      // Try to parse as ISO or common DB format
      const d = new Date(ts.replace(/-/g, '/').replace('T', ' '));
      if (!isNaN(d.getTime())) {
        const y = d.getFullYear();
        const m = String(d.getMonth()+1).padStart(2,'0');
        const day = String(d.getDate()).padStart(2,'0');
        const h = String(d.getHours()).padStart(2,'0');
        const min = String(d.getMinutes()).padStart(2,'0');
        return `${y}-${m}-${day} ${h}:${min}`;
      }
      return ts;
    }

    const html = items.map(i => {
      const last = i.last_result || {};
      const logo = last.courier ? courierKey(last.courier) : 'unknown';
      const daysHtml = (typeof last.days_taken === 'number') ? `<span class='badge bg-light text-secondary ms-2' style='border:1px solid #e0e0e0;'>${last.days_taken} day${last.days_taken === 1 ? '' : 's'}</span>` : '';
      const courierHtml = last.courier ? `<img src="/static/img/${logo}.svg" class="courier-logo-sm" alt="${last.courier}"> ${last.courier} — ${last.status || ''} ${daysHtml}` : daysHtml;
      const labelHtml = i.label ? `<span class="tracked-label small">${i.label}</span>` : '';
      const sc = statusClassFor(last.status);
      const details = detailsFor(last);
      return `
      <div class="card mt-2 ${sc}" data-id="${i.id}" tabindex="0" aria-expanded="false">
        <div class="card-body d-flex flex-column flex-md-row justify-content-between align-items-start align-items-md-center">
          <div class="w-100">
            <div class="d-flex align-items-center flex-wrap gap-2 mb-1">
              ${last.courier ? `<img src="/static/img/${logo}.svg" class="courier-logo-sm" alt="${last.courier}"> <span class="fw-semibold">${last.courier}</span>` : ''}
              <span class="ms-1"><strong>${i.tracking}</strong></span>
              ${labelHtml}
              ${daysHtml}
            </div>
            <div class="d-flex align-items-center flex-wrap gap-2">
              <span class="note">${last.status || ''}</span>
              <span class="last-checked-text ms-2">${i.last_checked ? 'last checked '+formatTimestamp(i.last_checked) : ''}</span>
            </div>
          </div>
          <div class="mt-2 mt-md-0">
            <button class="btn-delete-x" title="Remove" aria-label="Remove">&times;</button>
            <button class="btn btn-sm btn-outline-secondary me-2 btn-check">Check</button>
          </div>
        </div>
        ${details}
      </div>`;
    }).join('');

    trackedListDiv.innerHTML = html;

    // attach handlers
    trackedListDiv.querySelectorAll('.btn-check').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        e.stopPropagation();
        const card = e.target.closest('.card');
        const id = card.getAttribute('data-id');

        // show checking overlay
        card.classList.add('checking');
        const overlay = document.createElement('div');
        overlay.className = 'spinner-overlay';
        overlay.innerHTML = '<span class="spinner-border text-primary" role="status" aria-hidden="true"></span>';
        card.appendChild(overlay);

        e.target.disabled = true;
        try {
          await fetch(`/api/tracked/${id}/check`, { method: 'POST', headers: { 'X-User-Id': USER_ID } });
          // success flash
          card.classList.add('checked-success');
          setTimeout(()=> card.classList.remove('checked-success'), 1000);
        } catch (err) {
          // error flash (red)
          card.style.transition = 'background-color .2s ease';
          card.style.backgroundColor = 'rgba(220,53,69,0.08)';
          setTimeout(()=> card.style.backgroundColor = '', 1000);
        } finally {
          e.target.disabled = false;
          card.classList.remove('checking');
          if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
          renderTrackedList();
        }
      });
    });

    trackedListDiv.querySelectorAll('.btn-delete-x').forEach(btn=>{
      btn.addEventListener('click', async (e)=>{
        e.stopPropagation();
        const card = e.target.closest('.card');
        const id = card.getAttribute('data-id');
        if (!confirm('Remove tracking '+card.querySelector('strong').innerText+'?')) return;
        await fetch(`/api/tracked/${id}`, { method: 'DELETE', headers: { 'X-User-Id': USER_ID } });
        renderTrackedList();
      });
    });

    // Label edit handler (clicking label opens inline editor)
    trackedListDiv.querySelectorAll('.tracked-label').forEach(b=>{
      b.addEventListener('click', (e)=>{
        e.stopPropagation();
        const card = e.target.closest('.card');
        const id = card.getAttribute('data-id');
        const current = e.target.innerText || '';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = current;
        input.className = 'form-control form-control-sm d-inline-block';
        input.style.width = '180px';
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-sm btn-primary ms-2';
        saveBtn.innerText = 'Save';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-sm btn-outline-secondary ms-2';
        cancelBtn.innerText = 'Cancel';
        const container = document.createElement('span');
        container.appendChild(input);
        container.appendChild(saveBtn);
        container.appendChild(cancelBtn);
        e.target.parentNode.replaceChild(container, e.target);

        saveBtn.addEventListener('click', async () => {
          const newLabel = input.value.trim();
          const r = await fetch(`/api/tracked/${id}/label`, { method: 'POST', headers: {'Content-Type':'application/json', 'X-User-Id': USER_ID}, body: JSON.stringify({ label: newLabel }) });
          if (r.ok) renderTrackedList(); else alert('Failed to save label');
        });
        cancelBtn.addEventListener('click', () => renderTrackedList());
      });
    });

    // Expand/collapse behavior: clicking a card toggles its details and collapses others
    trackedListDiv.querySelectorAll('.card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('button')) return; // ignore button clicks
        const wasExpanded = card.classList.contains('expanded');
        // collapse others
        trackedListDiv.querySelectorAll('.card.expanded').forEach(c => {
          if (c !== card) {
            c.classList.remove('expanded');
            c.setAttribute('aria-expanded','false');
          }
        });

        if (wasExpanded) {
          card.classList.remove('expanded');
          card.setAttribute('aria-expanded','false');
        } else {
          card.classList.add('expanded');
          card.setAttribute('aria-expanded','true');
          // bring into view smoothly
          card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });

      // accessible keyboard toggling
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          card.click();
        }
      });
    });
  }

  // Ensure the tracked wrapper is visible immediately on load
  // so the user always sees their watchlist area without needing
  // to click anything.
  // Call renderTrackedList early to create the wrapper and fetch items.
  renderTrackedList();



  // small helper to show transient messages near the add controls
  function showAddMessage(text, type){
    try {
      const area = document.getElementById('add-message-area');
      if (!area) return;
      const a = document.createElement('div');
      a.className = `alert alert-${type} mt-2 py-1`;
      a.style.fontSize = '0.9rem';
      a.style.marginBottom = '0';
      a.innerText = text;
      area.appendChild(a);
      setTimeout(()=>{ a.classList.add('fade-out'); a.style.transition = 'opacity .5s ease'; a.style.opacity = '0'; setTimeout(()=> a.remove(), 600); }, 1800);
    } catch (err){ console.error('showAddMessage failed', err); }
  }

  // Fetch status keywords from server so client colors/filters match server
  fetch('/api/status_keywords')
    .then(r => r.json())
    .then(data => { STATUS_KEYWORDS = data; renderTrackedList(); })
    .catch(() => { renderTrackedList(); });
});
