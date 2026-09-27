/* Website chat widget. Embed with:
 *   <script src="https://YOUR-API/widget.js" data-key="wk_..." async></script>
 * Everything renders inside a shadow root, and all message text goes in through textContent. */
(function () {
  'use strict'
  var script = document.currentScript || document.querySelector('script[data-key][src*="widget.js"]')
  if (!script || window.__avnWidgetLoaded) return
  window.__avnWidgetLoaded = true
  var KEY = script.getAttribute('data-key')
  var API = new URL(script.src).origin
  var LIVEKIT_SRC = 'https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js'
  var STORE = 'avn-chat:' + KEY

  function load(k) { try { return JSON.parse(sessionStorage.getItem(STORE) || '{}')[k] } catch (e) { return undefined } }
  function save(k, v) {
    try { var s = JSON.parse(sessionStorage.getItem(STORE) || '{}'); s[k] = v; sessionStorage.setItem(STORE, JSON.stringify(s)) } catch (e) { /* private mode */ }
  }

  function call(method, path, body) {
    return fetch(API + path, {
      method: method,
      headers: body ? { 'Content-Type': 'application/json', 'X-Widget-Key': KEY } : { 'X-Widget-Key': KEY },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (res) {
      return res.json().catch(function () { return {} }).then(function (data) {
        if (!res.ok) throw new Error(data.detail || 'Something went wrong')
        return data
      })
    })
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag)
    for (var k in attrs || {}) node.setAttribute(k, attrs[k])
    if (text != null) node.textContent = text
    return node
  }

  call('GET', '/api/public/widget').then(start).catch(function (e) { console.warn('[chat widget]', e.message) })

  function start(cfg) {
    var color = /^#[0-9A-Fa-f]{6}$/.test(cfg.color) ? cfg.color : '#7B61FF'
    var host = el('div', { id: 'avn-chat-widget' })
    document.body.appendChild(host)
    var root = host.attachShadow ? host.attachShadow({ mode: 'open' }) : host
    var style = el('style')
    style.textContent = [
      ':host{all:initial}',
      '*{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}',
      '.bubble{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;background:' + color + ';color:#fff;box-shadow:0 6px 24px rgba(0,0,0,.25);z-index:2147483000;display:flex;align-items:center;justify-content:center}',
      '.bubble svg{width:26px;height:26px}',
      '.panel{position:fixed;right:20px;bottom:88px;width:min(370px,calc(100vw - 32px));height:min(540px,calc(100vh - 120px));background:#fff;color:#111;border-radius:16px;box-shadow:0 12px 48px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden;z-index:2147483000}',
      '.panel.open{display:flex}',
      '.head{background:' + color + ';color:#fff;padding:14px 16px;display:flex;align-items:center;gap:8px}',
      '.head b{flex:1;font-size:15px}',
      '.head button{background:rgba(255,255,255,.18);border:none;color:#fff;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:12.5px}',
      '.log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px;background:#f6f6f8}',
      '.msg{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}',
      '.agent{background:#fff;border:1px solid #e6e6ea;align-self:flex-start;border-bottom-left-radius:4px}',
      '.me{background:' + color + ';color:#fff;align-self:flex-end;border-bottom-right-radius:4px}',
      '.note{align-self:center;font-size:12px;color:#666;text-align:center}',
      '.form{background:#fff;border:1px solid #e6e6ea;border-radius:12px;padding:10px;display:flex;flex-direction:column;gap:6px;align-self:stretch}',
      '.form p{margin:0 0 2px;font-size:13px}',
      'input{border:1px solid #d6d6dc;border-radius:8px;padding:8px 10px;font-size:14px;width:100%;color:#111;background:#fff}',
      '.send{display:flex;gap:6px;padding:10px;border-top:1px solid #eee;background:#fff}',
      '.btn{background:' + color + ';color:#fff;border:none;border-radius:8px;padding:0 14px;cursor:pointer;font-size:14px;min-height:36px}',
      '.btn:disabled{opacity:.5;cursor:default}',
      '.typing{font-size:12px;color:#888;padding:0 14px 6px;background:#f6f6f8;min-height:18px}',
    ].join('')
    root.appendChild(style)

    var bubble = el('button', { class: 'bubble', 'aria-label': 'Chat with us', 'aria-expanded': 'false' })
    var svgNS = 'http://www.w3.org/2000/svg'
    var svg = document.createElementNS(svgNS, 'svg'); svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none')
    svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '2')
    var path = document.createElementNS(svgNS, 'path'); path.setAttribute('d', 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z')
    svg.appendChild(path); bubble.appendChild(svg)

    var panel = el('div', { class: 'panel', role: 'dialog', 'aria-label': cfg.name })
    var head = el('div', { class: 'head' })
    head.appendChild(el('b', null, cfg.agent_name || cfg.name))
    var voiceBtn = cfg.voice ? el('button', { type: 'button' }, 'Talk') : null
    if (voiceBtn) head.appendChild(voiceBtn)
    var closeBtn = el('button', { type: 'button', 'aria-label': 'Close chat' }, '✕')
    head.appendChild(closeBtn)
    var log = el('div', { class: 'log', 'aria-live': 'polite' })
    var typing = el('div', { class: 'typing' })
    var bar = el('form', { class: 'send' })
    var input = el('input', { type: 'text', placeholder: 'Type your message…', 'aria-label': 'Message', maxlength: '1000' })
    var sendBtn = el('button', { class: 'btn', type: 'submit' }, 'Send')
    bar.appendChild(input); bar.appendChild(sendBtn)
    panel.appendChild(head); panel.appendChild(log); panel.appendChild(typing); panel.appendChild(bar)
    root.appendChild(panel); root.appendChild(bubble)

    function add(role, text) {
      var m = el('div', { class: 'msg ' + (role === 'me' ? 'me' : role === 'note' ? 'note' : 'agent') }, text)
      log.appendChild(m); log.scrollTop = log.scrollHeight
      var history = load('history') || []
      if (role !== 'note') { history.push([role, text]); save('history', history.slice(-60)) }
    }

    var history = load('history') || []
    if (history.length) history.forEach(function (h) { log.appendChild(el('div', { class: 'msg ' + (h[0] === 'me' ? 'me' : 'agent') }, h[1])) })
    else add('agent', cfg.greeting)

    function toggle(open) {
      panel.classList.toggle('open', open)
      bubble.setAttribute('aria-expanded', String(open))
      if (open) { input.focus(); log.scrollTop = log.scrollHeight }
    }
    bubble.addEventListener('click', function () { toggle(!panel.classList.contains('open')) })
    closeBtn.addEventListener('click', function () { toggle(false) })

    var busy = false
    bar.addEventListener('submit', function (e) {
      e.preventDefault()
      var text = input.value.trim()
      if (!text || busy) return
      busy = true; sendBtn.disabled = true; input.value = ''
      add('me', text); typing.textContent = (cfg.agent_name || 'Assistant') + ' is typing…'
      call('POST', '/api/public/chat', { message: text, session: load('session') || undefined }).then(function (res) {
        if (res.session) save('session', res.session)
        add('agent', res.reply)
        if (res.ask_for_contact && !load('contact') && !root.querySelector('.form')) askContact()
      }).catch(function (err) {
        if (/ended|limit/i.test(err.message)) save('session', null)
        add('note', err.message)
      }).then(function () { busy = false; sendBtn.disabled = false; typing.textContent = ''; input.focus() })
    })

    function askContact() {
      var form = el('form', { class: 'form' })
      form.appendChild(el('p', null, 'Want us to follow up? Leave your details.'))
      var name = el('input', { placeholder: 'Your name', 'aria-label': 'Your name', required: '', maxlength: '100' })
      var phone = el('input', { placeholder: 'Phone number', 'aria-label': 'Phone number', required: '', type: 'tel', maxlength: '20' })
      var email = el('input', { placeholder: 'Email (optional)', 'aria-label': 'Email', type: 'email', maxlength: '100' })
      var ok = el('button', { class: 'btn', type: 'submit' }, 'Send details')
      ;[name, phone, email, ok].forEach(function (n) { form.appendChild(n) })
      form.addEventListener('submit', function (e) {
        e.preventDefault(); ok.disabled = true
        call('POST', '/api/public/chat/contact', { session: load('session'), name: name.value, phone: phone.value, email: email.value || null })
          .then(function () { save('contact', true); form.remove(); add('note', 'Thanks! We\'ll be in touch.') })
          .catch(function (err) { ok.disabled = false; add('note', err.message) })
      })
      log.appendChild(form); log.scrollTop = log.scrollHeight
    }

    // Voice: loads the LiveKit client only when the visitor asks to talk.
    var room = null
    function loadLiveKit() {
      if (window.LivekitClient) return Promise.resolve(window.LivekitClient)
      return new Promise(function (resolve, reject) {
        var s = document.createElement('script'); s.src = LIVEKIT_SRC; s.async = true
        s.onload = function () { resolve(window.LivekitClient) }; s.onerror = function () { reject(new Error('Voice could not load on this page.')) }
        document.head.appendChild(s)
      })
    }
    function hangUp() {
      if (room) { room.disconnect(); room = null }
      root.querySelectorAll('audio').forEach(function (a) { a.remove() })
      if (voiceBtn) voiceBtn.textContent = 'Talk'
    }
    if (voiceBtn) voiceBtn.addEventListener('click', function () {
      if (room) { hangUp(); add('note', 'Call ended'); return }
      voiceBtn.textContent = 'Connecting…'
      Promise.all([loadLiveKit(), call('POST', '/api/public/voice', { session: load('session') || undefined })]).then(function (r) {
        var LK = r[0], res = r[1]
        if (res.session) save('session', res.session)
        room = new LK.Room()
        room.on(LK.RoomEvent.TrackSubscribed, function (track) {
          if (track.kind === 'audio') root.appendChild(track.attach())
        })
        room.on(LK.RoomEvent.Disconnected, hangUp)
        return room.connect(res.url, res.token).then(function () { return room.localParticipant.setMicrophoneEnabled(true) })
      }).then(function () {
        voiceBtn.textContent = 'End call'; add('note', 'You\'re on a call. Speak any time.')
      }).catch(function (err) { hangUp(); add('note', err.message || 'Voice is unavailable.') })
    })
  }
})()
