"use strict";
const $ = id => document.getElementById(id);
const sites = ["youtube", "bilibili", "missevan"];
const labels = {youtube:"YouTube", bilibili:"Bilibili", missevan:"MissEvan"};
const voices = {ja:"ja-JP", zh:"zh-CN", en:"en-US", ko:"ko-KR"};
let token = new URLSearchParams(location.hash.slice(1)).get("token");
if (token) { sessionStorage.setItem("dashboard-token", token); history.replaceState(null, "", "/"); }
token = token || sessionStorage.getItem("dashboard-token");
let state, initialized = false, lastSpeech = 0, lastNotice = 0, audioEnabled = false;
let archives = [], lastChat = "", lastMonitor = "", lastRooms = "", lastObs = "", lastModeration = "";
const observedJobs = new Set(), jobHandlers = new Map();
const speechQueue = [];
let speaking = null;
let youtubeAccountPending = false;
let catalog = {languages:{en:"English"}, strings:{}}, language = "en", connectionText = "", pendingLanguage = null;
const staticText = [], staticAttributes = [];
function t(text, values = {}) {
  const translated = catalog.strings[language]?.[text] ?? text;
  return translated.replace(/\{(\w+)\}/g, (match, name) => name in values ? String(values[name]) : match);
}
// Static markup is recorded once in English, so switching languages never re-translates translated text.
function collectStaticText() {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const original = walker.currentNode.nodeValue, key = original.trim();
    if (key) staticText.push([walker.currentNode, original, key]);
  }
  for (const element of document.querySelectorAll("[placeholder],[aria-label],[title]"))
    for (const name of ["placeholder","aria-label","title"])
      if (element.hasAttribute(name)) staticAttributes.push([element, name, element.getAttribute(name)]);
}
function applyLanguage(next) {
  language = next in catalog.languages ? next : "en";
  document.documentElement.lang = {zh:"zh-CN",ja:"ja",en:"en"}[language] || "en";
  for (const [textNode, original, key] of staticText) textNode.nodeValue = original.replace(key, t(key));
  for (const [element, name, original] of staticAttributes) element.setAttribute(name, t(original));
  document.title = t("Streaming Dashboard");
  $("ui-language").value = language;
  if (connectionText) $("connection").textContent = t(connectionText);
  lastChat = lastMonitor = lastRooms = lastObs = lastModeration = "";
  if (state) {
    renderState();
    if (!$("analytics").hidden) loadAnalysisRooms().then(() => {
      if ($("analytics-room").value) return Promise.all([refreshAnalytics(), loadRoomEvents()]);
    }).catch(report);
  }
}
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function image(url, className, alt = "") {
  const result = node("img", undefined, className);
  result.src = url; result.alt = alt; result.referrerPolicy = "no-referrer"; result.loading = "lazy";
  return result;
}
function alertMessage(text, error = false) {
  const item = node("div", text, error ? "alert error" : "alert");
  $("alerts").prepend(item);
  while ($("alerts").children.length > 5) $("alerts").lastChild.remove();
  setTimeout(() => item.remove(), 15000);
}
async function api(path, body) {
  const response = await fetch(path, {
    method:body ? "POST" : "GET",
    headers:{"X-Dashboard-Token":token || "", ...(body ? {"Content-Type":"application/json"} : {})},
    ...(body ? {body:JSON.stringify(body)} : {}),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(t(result.error || `HTTP ${response.status}`));
  return result;
}
async function action(data) {
  try { return await api("/api/action", data); }
  catch (error) { alertMessage(error.message, true); error.reported = true; throw error; }
}
// Background actions return a job id; the handler runs once the polled state reports it done.
async function job(data, handler) {
  const result = await action(data);
  jobHandlers.set(result.job, handler || (() => alertMessage(t("Task completed"))));
  return result.job;
}
function report(error) { if (!error.reported) alertMessage(error.message || String(error),true); }
function bindForm(id, callback) {
  $(id).addEventListener("submit", async event => {
    event.preventDefault();
    const buttons = [...$(id).querySelectorAll("button")];
    buttons.forEach(button => button.disabled = true);
    try { await callback(); } catch (error) { report(error); }
    finally { buttons.forEach(button => button.disabled = false); }
  });
}
function bindClick(id, callback) {
  $(id).addEventListener("click", () => Promise.resolve().then(callback).catch(report));
}
function button(text, callback, danger = false) {
  const result = node("button", text, danger ? "danger" : "");
  result.type = "button";
  result.addEventListener("click", async () => {
    result.disabled = true;
    try { await callback(); } catch (error) { report(error); }
    finally { result.disabled = false; }
  });
  return result;
}
function checkbox(text, checked, onChange) {
  const input = node("input"); input.type = "checkbox"; input.checked = checked;
  const label = node("label", undefined, "check"); label.append(input, document.createTextNode(text));
  input.addEventListener("change", () => Promise.resolve().then(() => onChange(input.checked)).catch(error => {
    input.checked = !input.checked; report(error);
  }));
  return label;
}
function confirmAction(text) {
  return new Promise(resolve => {
    $("confirm-text").textContent = text;
    $("confirm").addEventListener("close", () => resolve($("confirm").returnValue === "ok"), {once:true});
    $("confirm").showModal();
  });
}
function roomName(room) { return state.statuses[room.id]?.room_name || room.target; }
function options(select, rooms, none = false) {
  const previous = select.value;
  select.replaceChildren();
  if (none) select.add(new Option(t("No room selected"), ""));
  for (const room of rooms) select.add(new Option(`${labels[room.platform]} · ${roomName(room)}`, room.id));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
function formValues(form) {
  const values = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    values[input.name] = input.type === "checkbox" ? input.checked
      : input.type === "number" || "number" in input.dataset ? Number(input.value) : input.value;
  }
  return values;
}
function fillForm(form) {
  for (const input of form.elements) {
    if (!input.name || !(input.name in state.settings)) continue;
    const value = state.settings[input.name];
    if (input.type === "checkbox") input.checked = value;
    else {
      if (input.tagName === "SELECT" && value !== "" && ![...input.options].some(option => option.value === String(value)))
        input.add(new Option(String(value), String(value)));
      input.value = value;
    }
  }
}
async function saveSettings(values) {
  await action({action:"settings", values});
  Object.assign(state.settings, values);
}
// ── Chat rooms (desktop: one selected room per site, plus show / send checkboxes) ─────────────
function refreshRooms() {
  const signature = JSON.stringify([state.targets, state.targets.map(roomName), state.rooms,
    state.settings.visible_sites, state.settings.send_sites]);
  if (signature === lastRooms) return;
  lastRooms = signature;
  $("room-selectors").replaceChildren();
  for (const site of sites) {
    const card = node("article", undefined, "room-card");
    const select = node("select");
    select.setAttribute("aria-label", t("{site} room", {site:labels[site]}));
    options(select, state.targets.filter(room => room.platform === site), true);
    select.value = state.rooms[site] || "";
    select.addEventListener("change", () => {
      clearSpeech();
      saveSettings({selected_rooms:{...state.rooms, [site]:select.value}}).then(() => {
        state.rooms[site] = select.value; lastChat = ""; renderChat();
      }).catch(() => { select.value = state.rooms[site] || ""; });
    });
    const toggle = (key, enabled) => {
      const list = state.settings[key].filter(item => item !== site);
      if (enabled) list.push(site);
      return saveSettings({[key]:sites.filter(item => list.includes(item))}).then(() => { lastChat = ""; renderChat(); });
    };
    card.append(node("h3", labels[site]), select,
      checkbox(t("Show"), state.settings.visible_sites.includes(site), enabled => toggle("visible_sites", enabled)),
      checkbox(t("Send"), state.settings.send_sites.includes(site), enabled => toggle("send_sites", enabled)));
    $("room-selectors").append(card);
  }
  options($("transcribe-room"), state.targets);
  $("overlay-rooms").replaceChildren(...sites.map(site => {
    const label = node("label", undefined, "check");
    const enabled = node("input"); enabled.type = "checkbox"; enabled.checked = true; enabled.dataset.site = site;
    const select = node("select"); select.dataset.overlayRoom = site;
    select.setAttribute("aria-label", t("Monitored {site} room shown in the overlay", {site:labels[site]}));
    options(select, state.targets.filter(room => room.platform === site), true);
    select.value = state.rooms[site] || "";
    label.append(enabled, document.createTextNode(labels[site]), select);
    return label;
  }));
}
// ── Feeds ─────────────────────────────────────────────────────────────────────────────────────
function appendReadings(parent, text, readings, start = 0, end = text.length) {
  if (!readings?.length) { parent.append(document.createTextNode(text.slice(start, end))); return; }
  let position = 0;
  for (const [base, reading] of readings) {
    const next = position + base.length;
    if (next > start && position < end) {
      const visible = base.slice(Math.max(0, start - position), Math.min(base.length, end - position));
      if (reading && position >= start && next <= end) {
        const ruby = node("ruby", visible);
        ruby.append(node("rt", reading)); parent.append(ruby);
      } else parent.append(document.createTextNode(visible));
    }
    position = next;
  }
}
function messageBody(message) {
  const body = node("div", undefined, "body"), text = message._text ?? message.text ?? "";
  const color = message.color;
  if (message.platform === "bilibili" && !message._paid
      && (typeof color === "number" || (typeof color === "string" && /^\d+$/.test(color)))
      && Number.isInteger(Number(color)) && Number(color) >= 0 && Number(color) < 0xffffff) {
    body.classList.add("platform-colored");
    body.style.color = `#${Number(color).toString(16).padStart(6, "0")}`;
    const rgb = Number(color), brightness = .2126 * (rgb >> 16) + .7152 * (rgb >> 8 & 255) + .0722 * (rgb & 255);
    body.style.setProperty("--chat-outline", brightness < 128 ? "#fff" : "#000");
  }
  const codes = Object.keys(message.emotes || {}).filter(code => code && text.includes(code)).sort((a,b) => b.length-a.length);
  let offset = 0;
  while (offset < text.length) {
    const matches = codes.map(code => ({code,index:text.indexOf(code,offset)})).filter(match => match.index >= 0).sort((a,b) => a.index-b.index);
    if (!matches.length) { appendReadings(body, text, message._text_readings, offset); break; }
    const match = matches[0];
    appendReadings(body, text, message._text_readings, offset, match.index);
    body.append(image(message.emotes[match.code], "emoji", match.code));
    offset = match.index + match.code.length;
  }
  return body;
}
function cardClass(message) {
  const type = String(message.type || "").toLowerCase();
  if (message.platform === "missevan" && message.is_super_admin) return "card-admin";
  if (["superchat","superchatevent","superstickerevent"].includes(type)) return "card-superchat";
  if (["gift","membershipgiftingevent","giftmembershipreceivedevent"].includes(type)) return "card-gift";
  if (type === "newsponsorevent") return "card-member";
  return "";
}
function flags(message) {
  const result = [];
  if (message.is_owner) result.push("OWNER");
  if (message.platform === "missevan" && message.is_super_admin) result.push(t("Super admin"));
  else if (message.platform === "missevan" && message.is_moderator) result.push(t("Room admin"));
  else if (message.is_moderator) result.push("MOD");
  if (message.is_verified) result.push("VERIFIED");
  if (message.membership && !message.membership_icon) result.push(String(message.membership));
  if (message._thanked) result.push("THANKED");
  return result;
}
function copyText(message) {
  let line = `${message._time} [${String(message.platform || "").toUpperCase()}] ${message.author || "?"}: ${message.text || ""}`;
  if (String(message.translation || "").trim()) line += `\n  Translation: ${String(message.translation).trim()}`;
  return line;
}
function messageActions(message) {
  const actions = node("div", undefined, "actions");
  const run = command => job({action:"message", command, id:message._html_id}, result => {
    if (command === "mute") alertMessage(t("Muted {name} in Bilibili.", {name:result.muted || message.author}));
  });
  actions.append(button(t("Block"), async () => { await action({action:"message", command:"block", id:message._html_id}); lastChat = ""; }));
  actions.append(button(t("Read"), async () => {
    audioEnabled = true;
    await action({action:"message", command:"read", id:message._html_id});
  }));
  if (message._paid) actions.append(button(t("Thank"), () => action({action:"message", command:"thank", id:message._html_id})));
  if (message.platform === "bilibili") actions.append(button(t("Mute"), async () => {
    if (await confirmAction(t("Mute {name} in the active Bilibili room?", {name:message.author || t("this viewer")}))) await run("mute");
  }, true));
  actions.append(button(t("Copy"), async () => { await navigator.clipboard.writeText(copyText(message)); alertMessage(t("Copied")); }));
  return actions;
}
function messageRow(message, paid) {
  const row = node("div", undefined, ["message", paid ? "paid" : "", cardClass(message)].filter(Boolean).join(" "));
  if (message.avatar) row.append(image(message.avatar, "avatar"));
  else row.append(node("span", (message.author || "?").slice(0, 1).toUpperCase(), "avatar placeholder"));
  const content = node("div", undefined, "content");
  const meta = node("div", undefined, "meta");
  const author = node("strong");
  appendReadings(author, message.author || "?", message._author_readings);
  meta.append(document.createTextNode(`${message._time}  [${String(message.platform || "").toUpperCase()}]  `), author);
  const flagList = flags(message);
  if (flagList.length) meta.append(document.createTextNode(`  (${flagList.join(" · ")})`));
  if (message.membership_icon) meta.append(image(message.membership_icon, "badge-icon", message.membership || ""));
  const medal = message.platform === "bilibili" && message.fan_medal && typeof message.fan_medal === "object" ? message.fan_medal : null;
  if (medal && Number(medal.level) > 0) {
    const text = `${medal.name || "粉丝牌"} Lv.${Number(medal.level)}`, color = Number(medal.color) || 0;
    const badge = node("span", ` [${text}]`, "medal"); badge.title = text;
    if (color > 0 && color <= 0xffffff) badge.style.color = `#${color.toString(16).padStart(6, "0")}`;
    meta.append(badge);
  }
  content.append(meta, messageBody(message));
  const animate = state.settings.gift_effects && message.type === "gift";
  const imageUrl = (animate && message.gift_animation_url) || message.sticker_url;
  if (imageUrl) content.append(image(imageUrl, "gift", message.gift_name || t("Gift / sticker")));
  if (message.translation) content.append(node("div", `🌐 ${message.translation}`, "translation"));
  if (message._amount) content.append(node("div", message._amount, "amount"));
  content.append(messageActions(message));
  row.append(content);
  return row;
}
function fillFeed(feed, rows) {
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
  feed.replaceChildren(...rows);
  if (!feed.children.length) feed.append(node("p", t("Waiting for messages…")));
  if (nearBottom) feed.scrollTop = feed.scrollHeight;
}
function renderChat() {
  const signature = JSON.stringify([state.messages, state.paid, state.joins, state.settings.gift_effects]);
  // Rebuilding the feed would drop a text selection.
  if (signature === lastChat || window.getSelection()?.toString()) return;
  lastChat = signature;
  fillFeed($("chat-feed"), state.messages.map(message => messageRow(message, false)));
  fillFeed($("paid-feed"), state.paid.map(message => messageRow(message, true)));
  fillFeed($("join-feed"), state.joins.map(message => {
    const row = node("div"), template = t("{author} entered"), author = message.author || "?";
    const [before, after] = template.split("{author}");
    row.append(document.createTextNode(`${message._time}  [${String(message.platform || "").toUpperCase()}]  ${before}`));
    appendReadings(row, author, message._author_readings);
    row.append(document.createTextNode(after || ""));
    return row;
  }));
}
// ── Browser speech queue (desktop: Skip speech / Clear all speech) ─────────────────────────────
function speechStatus() { $("speech-status").textContent = t("Speech queue: {count}", {count:speechQueue.length + (speaking ? 1 : 0)}); }
function pumpSpeech() {
  if (speaking || !speechQueue.length || !("speechSynthesis" in window)) { speechStatus(); return; }
  const entry = speechQueue.shift();
  const text = state.settings.tts_skip_name
    ? entry.text_without_name ?? entry.text : entry.text_with_name ?? entry.text;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = voices[entry.language] || "en-US";
  utterance.rate = state.settings.tts_rate / 150;
  utterance.volume = state.settings.tts_volume / 100;
  const done = () => { if (speaking === utterance) { speaking = null; pumpSpeech(); } };
  utterance.onend = done; utterance.onerror = done;
  speaking = utterance; speechStatus();
  speechSynthesis.speak(utterance);
}
function clearSpeech() {
  speechQueue.length = 0;
  if (speaking && "speechSynthesis" in window) { speaking = null; speechSynthesis.cancel(); }
  speechStatus();
}
function queueSpeech() {
  for (const entry of state.speech) {
    if (entry.id <= lastSpeech) continue;
    lastSpeech = entry.id;
    const selected = entry.manual || (state.settings.tts_enabled && state.rooms[entry.platform] === entry.room
      && state.settings.visible_sites.includes(entry.platform));
    if (audioEnabled && selected) {
      speechQueue.push(entry);
      if (speechQueue.length > 50) speechQueue.shift();
    }
  }
  pumpSpeech();
}
// ── Monitoring / accounts ─────────────────────────────────────────────────────────────────────
function renderMonitor() {
  const signature = JSON.stringify([state.targets, state.statuses, state.recording,
    state.record_armed, state.bilibili_gift_revenue]);
  if (signature === lastMonitor) return;
  lastMonitor = signature; $("monitor-cards").replaceChildren();
  for (const room of state.targets) {
    const info = state.statuses[room.id] || {};
    const card = node("article");
    card.title = monitorTooltip(room, info, state.bilibili_gift_revenue?.[room.id]);
    card.append(node("h2", `${labels[room.platform]} · ${info.room_name || room.target}`));
    card.append(node("p", info.title || t("Waiting for room status")));
    const detail = node("div");
    const dot = node("span", undefined, `dot ${info.live === true ? "live" : info.live === false ? "offline" : ""}`);
    dot.title = t(info.live === true ? "Live" : info.live === false ? "Offline" : "Checking");
    detail.append(dot, document.createTextNode(`ID ${room.target}`)); card.append(detail);
    card.append(node("p", `${t("Audience: {count}", {count:info.viewers || 0})} · ${t(info.connection || "Connecting")}`));
    if (info.error) card.append(node("p", t(info.error)));
    const controls = node("div", undefined, "toolbar");
    controls.append(checkbox(t("Allow saving"), room.enabled, enabled => action({action:"allow_saving",room:room.id,enabled})));
    controls.append(button(t(state.record_armed.includes(room.id) ? "Disarm recording" : "Record"), () =>
      job({action:"record",room:room.id,enabled:!state.record_armed.includes(room.id)}, () => {})));
    controls.append(button(t("Remove"), async () => {
      if (await confirmAction(t("Remove this monitor and stop its recording?"))) await action({action:"remove_room",room:room.id});
    }, true));
    card.append(controls);
    const recording = state.recording[room.id];
    if (recording?.label) { const line = node("p", recording.label, "recording"); line.title = recording.detail; card.append(line); }
    $("monitor-cards").append(card);
  }
}
function monitorTooltip(room, info, giftRevenue = "") {
  const lines = [`ID ${room.target}`];
  if (info.viewers !== "" && info.viewers != null)
    lines.push(t(room.platform === "bilibili" ? " · {count} room audience" : " · {count} viewers", {count:info.viewers}));
  if (room.platform === "bilibili") {
    const audience = info.room_audience;
    lines.push(audience == null
      ? t("Room audience: waiting for live data")
      : t("Room audience: {value}", {value:audience}));
    if (info.guard_count != null) lines.push(t("Great Fleet: {value}", {value:info.guard_count}));
    if (info.popularity !== "" && info.popularity != null)
      lines.push(t("Popularity: {value}", {value:info.popularity}));
    lines.push(t("Captured gift revenue (session): {value}", {value:giftRevenue || "¥0"}));
    const parent = String(info.parent_area_name || "").trim();
    const area = String(info.area_name || "").trim();
    const zone = parent && area && parent !== area ? `${parent} / ${area}` : area || parent;
    if (zone) lines.push(t("Zone: {zone}", {zone}));
  } else if (room.platform === "missevan") {
    for (const [key, label] of [
      ["attention_count", "Attention count: {value}"], ["vip", "VIP: {value}"],
      ["score", "Score / popularity: {value}"], ["revenue", "Revenue: {value}"],
    ]) {
      if (info[key] !== "" && info[key] != null) lines.push(t(label, {value:info[key]}));
    }
  }
  return lines.join("\n");
}
function renderLogins() {
  const account = $("youtube-account"), youtube = state.logins.youtube;
  if (!youtube.signed_in) account.replaceChildren(new Option(t("Default account"), ""));
  if (!youtubeAccountPending) {
    const selected = youtube.page_id || "";
    if (![...account.options].some(option => option.value === selected))
      account.add(new Option(selected, selected));
    account.value = selected;
  }
  $("login-status").textContent = sites.map(site => {
    const login = state.logins[site];
    if (!login.signed_in) return t("{site}: not signed in", {site:labels[site]});
    const name = site === "youtube" && login.page_id && account.value === login.page_id
      ? account.selectedOptions[0]?.textContent || login.name : login.name;
    return name ? t("{site}: signed in as {name}", {site:labels[site], name}) : t("{site}: signed in", {site:labels[site]});
  }).join(" · ");
  $("find-accounts").disabled = account.disabled = !youtube.signed_in || youtubeAccountPending;
}
function reportLoginImport(result) {
  const parts = [];
  for (const site of sites) {
    const login = result.signed_in[site];
    if (login) parts.push(login.name ? t("{site}: signed in as {name}", {site:labels[site], name:login.name}) : t("{site}: signed in", {site:labels[site]}));
    else parts.push(`${labels[site]}: ${t(result.failed[site] || "No login cookies found.")}`);
  }
  for (const [browser, error] of Object.entries(result.browser_errors || {})) parts.push(`${browser}: ${error}`);
  const count = Object.keys(result.signed_in).length;
  alertMessage(`${t("Signed in to {count} of 3 sites.", {count})} ${parts.join(" · ")}`, count === 0);
}
function showAccounts(result) {
  const select = $("youtube-account");
  select.replaceChildren(new Option(t("Default account"), ""));
  result.channels.forEach((channel, index) => {
    const name = channel.name || "", handle = channel.handle || "";
    const label = name && handle && handle !== name ? `${name} (${handle})` : name || handle || t("YouTube channel {index}", {index:index + 1});
    if (channel.page_id) select.add(new Option(label, channel.page_id));
    else select.options[0].textContent = label;
  });
  state.logins.youtube.page_id = result.selected;
  select.value = [...select.options].some(option => option.value === result.selected) ? result.selected : "";
  renderLogins();
  alertMessage(t("Found {count} YouTube accounts / channels.", {count:result.channels.length}));
}
// ── Moderation ───────────────────────────────────────────────────────────────────────────────
function renderModeration() {
  const signature = JSON.stringify(state.filters);
  if (signature === lastModeration) return;
  lastModeration = signature;
  const row = (text, remove) => { const item = node("div", undefined, "toolbar"); item.append(node("code", text), button(t("Remove"), remove)); return item; };
  $("filter-list").replaceChildren(...state.filters.block_patterns.map(pattern => row(pattern, () => action({action:"moderation",pattern,remove:true}))));
  $("allow-list").replaceChildren(...state.filters.allow_patterns.map(pattern => row(pattern, () => action({action:"moderation",pattern,allow:true,remove:true}))));
  $("blocked-list").replaceChildren(
    ...Object.entries(state.filters.blocked_users).map(([key, name]) => row(name ? `${name} (${key})` : key, () => action({action:"moderation",unblock:key,kind:"user"}))),
    ...state.filters.blocked_names.map(name => row(name, () => action({action:"moderation",unblock:name,kind:"name"}))));
  for (const list of ["filter-list","allow-list","blocked-list"]) if (!$(list).children.length) $(list).append(node("p", t("None")));
}
// ── OBS ──────────────────────────────────────────────────────────────────────────────────────
function renderObs() {
  const obs = state.obs, signature = JSON.stringify([obs, state.settings.obs_enabled, state.settings.obs_chat_enabled, state.settings.obs_chat_source]);
  if (signature === lastObs) return;
  lastObs = signature;
  const connected = state.settings.obs_enabled && obs.connected;
  $("obs-controls").hidden = !connected;
  $("obs-status").textContent = !state.settings.obs_enabled ? t("OBS functions are off.") : connected ? t("OBS connected ✓") : obs.error || t("Not connected");
  $("obs-hint").textContent = connected ? "" : obs.hint || "";
  if (!connected) return;
  const status = obs.status || {};
  $("obs-metrics").replaceChildren(...[["CPU", `${status.cpu_usage ?? 0}%`], ["RAM", `${status.memory_usage ?? 0} MB`],
    ["FPS", `${status.fps ?? 0}`], ["Dropped Frames", `${status.output_skipped_frames ?? 0}`]].map(([title, value]) => {
    const card = node("article", undefined, "metric"); card.append(node("h3", t(title)), node("strong", value)); return card;
  }));
  $("obs-stream-state").textContent = t(status.streaming ? "Streaming is LIVE" : "Not streaming");
  $("obs-stream").textContent = t(status.streaming ? "⏹ Stop Stream" : "▶️ Start Stream");
  $("obs-stream").dataset.command = status.streaming ? "stop_stream" : "start_stream";
  $("obs-record-state").textContent = t(status.recording ? "Recording in progress" : "Not recording");
  $("obs-record").textContent = t(status.recording ? "⏹ Stop Recording" : "▶️ Start Recording");
  $("obs-record").dataset.command = status.recording ? "stop_record" : "start_record";
  if (document.activeElement !== $("scene")) {
    $("scene").replaceChildren(...(obs.scenes || []).map(name => new Option(name, name)));
    $("scene").value = obs.current_scene || "";
  }
  $("obs-sources").replaceChildren(...(obs.sources || []).map(source => checkbox(source.name, source.visible, visible =>
    job({action:"obs", command:"source", scene:obs.current_scene, name:source.name, visible}, () => {}))));
  const textSources = obs.text_sources || [];
  for (const select of [$("obs-chat-source"), $("source")]) {
    if (document.activeElement === select) continue;
    const previous = select === $("source") ? select.value : state.settings.obs_chat_source;
    select.replaceChildren(...textSources.map(name => new Option(name, name)));
    if (textSources.includes(previous)) select.value = previous;
  }
  $("obs-chat-source").closest("label").hidden = !state.settings.obs_chat_enabled || !textSources.length;
  let warning = "";
  if (state.settings.obs_chat_enabled) warning = obs.text_error || (!textSources.length ? t("Add a Text source in OBS to display chat.") : "");
  $("obs-text-warning").textContent = warning;
  // Desktop picks the first Text source when the saved one no longer exists.
  if (state.settings.obs_chat_enabled && textSources.length && !textSources.includes(state.settings.obs_chat_source))
    saveSettings({obs_chat_source:textSources[0]}).catch(() => {});
}
// ── Analytics ────────────────────────────────────────────────────────────────────────────────
let eventCursor = null;
function analysisRoom() {
  const room = $("analytics-room").value;
  if (!room) throw new Error(t("Select a room for analysis."));
  return room;
}
async function loadAnalysisRooms() {
  const rooms = await action({action:"event_rooms"}), select = $("analytics-room"), previous = select.value;
  const choices = new Map(rooms.map(item => [item.room, item.room]));
  for (const room of state.targets) choices.set(room.id, `${labels[room.platform]} · ${roomName(room)} (${room.target})`);
  select.replaceChildren(new Option(t("Select a room for analysis."), ""),
    ...[...choices].map(([value, name]) => new Option(name, value)));
  if (choices.has(previous)) select.value = previous;
  else clearRoomAnalysis();
}
function clearRoomAnalysis() {
  eventCursor = null;
  $("analytics-summary").textContent = t("Select a room for analysis.");
  $("analytics-rows").replaceChildren();
  $("event-rows").replaceChildren();
  $("events-older").disabled = true;
}
async function refreshAnalytics() {
  const room = analysisRoom(), result = await action({action:"analytics", room});
  if ($("analytics-room").value !== room) return;
  const viewers = result.viewers.map(item => t("Last recorded viewers: {now} / peak: {peak}", {
    now:item.now.toLocaleString(), peak:item.peak.toLocaleString()}));
  $("analytics-summary").textContent = [room, t("Recorded events: {count}", {count:result.events}), ...viewers].join(" · ");
  $("analytics-rows").replaceChildren(...result.rows.map(values => {
    const row = node("tr");
    values.forEach((value, index) => row.append(node("td", index === 0 || index === 3 ? t(String(value)) : String(value))));
    return row;
  }));
  if (!result.rows.length) { const row = node("tr"); row.append(node("td", t("No messages yet."))); $("analytics-rows").append(row); }
}
async function exportHotspots(format) {
  await saveSettings(formValues($("analytics-form")));
  const result = await action({action:"export_hotspots", format, room:analysisRoom()});
  download(result.text, result.filename, format === "csv" ? "text/csv;charset=utf-8" : "text/plain;charset=utf-8");
}
async function loadRoomEvents(older = false) {
  const room = analysisRoom();
  const result = await action({action:"room_events", room, before:older ? eventCursor : 0});
  if ($("analytics-room").value !== room) return;
  eventCursor = result.next;
  $("events-older").disabled = eventCursor === null;
  $("event-rows").replaceChildren(...result.events.map(event => {
    const row = node("tr"), details = node("details");
    const payload = event.payload;
    details.append(node("summary", payload.text || payload.author || JSON.stringify(payload)),
      node("pre", JSON.stringify(event, null, 2)));
    row.append(node("td", new Date(event.received_at * 1000).toLocaleString()),
      node("td", t(event.kind)));
    const cell = node("td"); cell.append(details); row.append(cell);
    return row;
  }));
}
// ── Emotes ───────────────────────────────────────────────────────────────────────────────────
function insertText(text) {
  const input = $("send-text"), start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? start;
  input.value = `${input.value.slice(0, start)}${text}${input.value.slice(end)}`.slice(0, 500);
  input.focus(); input.selectionStart = input.selectionEnd = Math.min(500, start + text.length);
}
async function useEmote(site, entry) {
  if (site === "youtube") {
    insertText(entry.code || entry.label);
    if (!state.settings.send_sites.includes("youtube")) await saveSettings({send_sites:sites.filter(item => item === "youtube" || state.settings.send_sites.includes(item))});
    lastRooms = "";
  } else if (site === "kaomoji") {
    $("emotes").close();
    insertText(entry.value || entry.label);
  }
  else await job({action:"use_emote", site, unique:entry.unique, package_id:entry.package_id, sticker_id:entry.sticker_id},
    () => {
      $("emotes").close();
      alertMessage(t("Sent {name}", {name:entry.label}));
    });
}
function showEmotes(result) {
  if (result.site !== $("emote-site").value) return;
  $("emote-status").textContent = result.error ? t(result.error) : result.groups.length ? "" : t("No emotes are available for this room.");
  $("emote-list").replaceChildren(...result.groups.map(group => {
    const section = node("section", undefined, "emote-group"), grid = node("div", undefined, "emote-grid");
    section.append(node("h3", t(group.name)), grid);
    for (const entry of group.entries) {
      const item = button(entry.image ? "" : entry.label, () => useEmote(result.site, entry));
      if (entry.image) item.append(image(entry.image, "emote", entry.label));
      item.title = entry.locked && entry.hint ? `${entry.label}\n${entry.hint}` : entry.label;
      if (entry.locked) { item.disabled = true; item.classList.add("locked"); }
      grid.append(item);
    }
    return section;
  }));
}
async function loadEmotes() {
  $("emote-status").textContent = t("Loading…"); $("emote-list").replaceChildren();
  await job({action:"emotes", site:$("emote-site").value}, showEmotes);
}
// ── Archive / misc ───────────────────────────────────────────────────────────────────────────
function renderArchives() {
  const current = archives.find(item => item.session_id === $("archive-session").value);
  $("archive-rows").replaceChildren();
  for (const message of current?.messages || []) {
    const row = node("tr");
    for (const key of ["timestamp","platform","author","text"]) row.append(node("td", message[key] || ""));
    $("archive-rows").append(row);
  }
}
function showArchives(result) {
  archives = result; const previous = $("archive-session").value; $("archive-session").replaceChildren();
  for (const session of archives) $("archive-session").add(new Option(
    `${session.room_name || session.channel_id || session.room_id || session.session_id} · ${t("{count} shown", {count:session.messages.length})}`, session.session_id));
  if (archives.some(session => session.session_id === previous)) $("archive-session").value = previous;
  renderArchives();
}
function tsv() {
  const current = archives.find(item => item.session_id === $("archive-session").value);
  if (!current) throw new Error(t("Select a saved room first."));
  return [[t("Time"),t("Platform"),t("Author"),t("Message")], ...current.messages.map(message =>
    ["timestamp","platform","author","text"].map(key => String(message[key] || "").replace(/[\t\r\n]+/g, " ")))].map(row => row.join("\t")).join("\n");
}
function download(text, filename, type) {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const link = node("a"); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function processJobs() {
  for (const [id, entry] of Object.entries(state.jobs)) {
    if (entry.status === "running" || observedJobs.has(id)) continue;
    observedJobs.add(id);
    const handler = jobHandlers.get(id);
    jobHandlers.delete(id);
    if (!handler) continue;
    if (entry.status === "failed") {
      alertMessage(t(entry.error), true);
      if (["transcription_models","transcription_test"].includes(entry.kind))
        setTranscriptApiResult(entry.error);
    }
    else handler(entry.result);
  }
}
function showSendResults(results) {
  const parts = Object.entries(results).map(([site, result]) =>
    `${labels[site]}: ${result.ok ? t("sent") : `${t("failed")} ${t(result.error)}`.trim()}`);
  alertMessage(parts.join(" · "), !Object.values(results).some(result => result.ok));
}
let transcriptCleared = 0;
let transcriptApiResult = null;
function setTranscriptApiResult(text, values = {}) {
  transcriptApiResult = {text, values};
  $("transcribe-api-result").textContent = t(text, values);
}
function renderTranscript() {
  const credentials = state.transcription_api;
  $("transcribe-key-status").textContent = credentials?.error ? t(credentials.error) :
    t(credentials?.key_saved ? "API key saved. Leave blank to keep it." : "No API key saved. Optional for keyless services.");
  if (transcriptApiResult)
    $("transcribe-api-result").textContent = t(transcriptApiResult.text, transcriptApiResult.values);
  const transcript = state.transcription;
  const transcriptStatus = {idle:"Idle", resolving_stream:"Resolving stream", loading_model:"Loading model", connecting:"Connecting",
    listening:"Listening", stopping:"Stopping", stopped:"Stopped", ended:"Ended", failed:"Failed"};
  $("transcribe-status").textContent = transcript ? `${t(transcriptStatus[transcript.status] || transcript.status)} ${transcript.error || ""}` : t("Idle");
  const all = transcript?.segments || [];
  if (all.length < transcriptCleared) transcriptCleared = 0;
  const segments = all.slice(transcriptCleared);
  $("transcript").textContent = segments.map(segment =>
    `${segment.original || ""}${segment.translated ? "\n"+segment.translated : ""}${segment.translation_error ? "\n"+t("Translation failed: {error}", {error:segment.translation_error}) : ""}`
  ).join("\n");
}
function renderState() {
  if (!initialized) {
    for (const form of document.querySelectorAll("[data-settings]")) fillForm(form);
    lastSpeech = Math.max(0, ...state.speech.map(entry => entry.id));
    lastNotice = Math.max(0, ...state.notifications.map(notice => notice.id));
    for (const id of Object.keys(state.jobs)) observedJobs.add(id);
    initialized = true;
  }
  // Another browser tab may have switched the interface language.
  if (!pendingLanguage && state.settings.ui_language !== language) applyLanguage(state.settings.ui_language);
  refreshRooms(); renderChat(); renderMonitor(); renderLogins(); renderModeration(); renderObs(); renderTranscript(); processJobs();
  $("event-recording-status").textContent = state.event_recording.error
    ? t("Room event recording failed: {error}", {error:state.event_recording.error})
    : t("Recording events for all monitored rooms.");
  $("event-recording-status").className = state.event_recording.error ? "warning" : "";
  for (const notice of state.notifications) if (notice.id > lastNotice) {
    const {heading, body} = liveNotificationText(notice);
    alertMessage(body ? `${heading} · ${body}` : heading);
    if ("Notification" in window && Notification.permission === "granted") new Notification(heading, {body});
    showLiveNotification(notice);
    lastNotice = notice.id;
  }
  queueSpeech();
}
function liveNotificationText(notice) {
  const name = notice.channel || notice.name || notice.room || notice.platform || t("Streaming Dashboard");
  return {name, heading:t("{name} is live", {name}), body:notice.detail || notice.title || ""};
}
function showLiveNotification(notice) {
  const url = typeof notice.url === "string" && notice.url.startsWith("https://") ? notice.url : "";
  const card = node("article", undefined, "live-notification");
  const header = node("div", undefined, "live-notification-header");
  header.append(node("span", "▶"), node("strong", t("Streaming Dashboard")));
  const close = node("button", "×", "live-notification-close");
  close.type = "button"; close.setAttribute("aria-label", t("Dismiss notification"));
  header.append(close);
  const {name, heading, body} = liveNotificationText(notice);
  const title = node("h2", heading);
  const detail = node("p", [notice.platform, body].filter(Boolean).join(" · "), "details");
  card.append(header, title, detail);
  const thumbnail = typeof notice.thumbnail === "string" && notice.thumbnail.startsWith("https://")
    ? notice.thumbnail : "";
  if (thumbnail) card.append(image(thumbnail, "", `${name} thumbnail`));
  if (url) {
    const open = node("a", t("Open live stream"), "open-live");
    open.href = url; open.target = "_blank"; open.rel = "noopener noreferrer";
    card.append(open);
  }
  const remove = () => {
    clearTimeout(timer);
    card.remove();
  };
  close.addEventListener("click", remove);
  $("live-notifications").append(card);
  const timer = setTimeout(remove, 20000);
  while ($("live-notifications").children.length > 5)
    $("live-notifications").firstElementChild.remove();
}
document.querySelectorAll("[data-tab]").forEach(tab => tab.addEventListener("click", () => {
  document.querySelectorAll(".panel").forEach(panel => panel.hidden = panel.id !== tab.dataset.tab);
  document.querySelectorAll("[data-tab]").forEach(button => button.classList.toggle("active",button === tab));
  if (tab.dataset.tab === "analytics") loadAnalysisRooms().then(() => {
    if ($("analytics-room").value) return Promise.all([refreshAnalytics(), loadRoomEvents()]);
  }).catch(report);
}));
bindClick("theme", () => { document.body.classList.toggle("light"); localStorage.setItem("html-theme",document.body.classList.contains("light") ? "light" : "dark"); });
if (localStorage.getItem("html-theme") === "light") document.body.classList.add("light");
bindForm("room-form", async () => { await action({action:"add_room",platform:$("platform").value,target:$("target").value}); $("target").value = ""; });
let settingsSaveQueue = Promise.resolve();
function queueSettingsSave(callback) {
  const result = settingsSaveQueue.then(callback);
  settingsSaveQueue = result.catch(() => {});
  return result;
}
for (const id of ["settings-form", "recognition-settings-form", "translation-preferences-form"])
  $(id).addEventListener("submit", event => event.preventDefault());
for (const form of document.querySelectorAll("[data-autosave]"))
  form.addEventListener("change", event => {
    const input = event.target, name = input.name;
    if (!name) return;
    if (!input.reportValidity()) return;
    const value = formValues(form)[name];
    queueSettingsSave(() => saveSettings({[name]:value})).then(() => {
      lastObs = lastChat = "";
    }).catch(error => {
      report(error);
      if (formValues(form)[name] === value) {
        if (input.type === "checkbox") input.checked = state.settings[name];
        else input.value = state.settings[name];
      }
    });
  });
$("ui-language").addEventListener("change", async () => {
  const previous = language, next = $("ui-language").value, request = pendingLanguage = {};
  applyLanguage(next);
  try { await action({action:"settings",values:{ui_language:next}}); if (pendingLanguage === request) state.settings.ui_language = next; }
  catch (error) { if (pendingLanguage === request) applyLanguage(previous); report(error); }
  finally { if (pendingLanguage === request) pendingLanguage = null; }
});
bindForm("cookie-form", async () => {
  await job({action:"import_cookies",text:$("cookie-text").value}, reportLoginImport);
  $("cookie-text").value = "";
  alertMessage(t("Checking cookies for YouTube, Bilibili and MissEvan…"));
});
bindClick("clear-cookies", () => action({action:"clear_login",site:$("cookie-site").value}));
bindClick("find-accounts", () => job({action:"youtube_accounts"}, showAccounts));
$("youtube-account").addEventListener("change", async () => {
  const pageId = $("youtube-account").value;
  youtubeAccountPending = true;
  renderLogins();
  try {
    const result = await action({action:"youtube_account", page_id:pageId});
    state.logins.youtube.page_id = result.page_id;
    alertMessage(t("YouTube account selected."));
  } catch (error) { report(error); }
  finally { youtubeAccountPending = false; renderLogins(); }
});
bindForm("send-form", async () => {
  const selected = state.settings.send_sites;
  if (!selected.length) throw new Error(t("Choose at least one site to send to."));
  await job({action:"send", sites:selected, text:$("send-text").value}, showSendResults);
  $("send-text").value = "";
});
bindForm("filter-form", async () => { await action({action:"moderation",pattern:$("pattern").value}); $("pattern").value = ""; });
bindClick("add-allow", async () => {
  if (!$("pattern").value.trim()) throw new Error(t("Enter a pattern of at most 300 characters."));
  await action({action:"moderation",pattern:$("pattern").value,allow:true}); $("pattern").value = "";
});
bindClick("clear-chat", async () => { if (await confirmAction(t("Clear the live feed? Saved chat will not be deleted."))) await action({action:"clear_chat"}); });
bindClick("skip-speech", () => { if (speaking && "speechSynthesis" in window) { speaking = null; speechSynthesis.cancel(); } pumpSpeech(); });
bindClick("clear-speech", clearSpeech);
bindClick("enable-audio", () => { audioEnabled = true; alertMessage(t("Browser speech enabled. Also enable reading in Settings.")); });
bindClick("notifications", async () => { if ("Notification" in window) alertMessage(t("Notifications: {permission}", {permission:await Notification.requestPermission()})); else alertMessage(t("This browser does not support notifications."),true); });
bindClick("open-emotes", () => { $("emotes").showModal(); return loadEmotes(); });
bindClick("emote-load", loadEmotes);
$("emote-site").addEventListener("change", () => loadEmotes().catch(report));
bindClick("archive-reload", () => job({action:"archives"}, showArchives));
$("archive-session").addEventListener("change",renderArchives);
bindClick("archive-copy", async () => { await navigator.clipboard.writeText(tsv()); alertMessage(t("Copied table")); });
bindClick("archive-export", () => download(tsv(),"saved-chat.tsv","text/tab-separated-values;charset=utf-8"));
bindClick("archive-delete", async () => { if (await confirmAction(t("Permanently delete all saved messages for this room?"))) await job({action:"delete_archive",session:$("archive-session").value}, showArchives); });
document.querySelectorAll("[data-obs]").forEach(control => control.addEventListener("click", () =>
  job({action:"obs",command:control.dataset.obs}, () => { lastObs = ""; alertMessage(t("OBS connected ✓")); }).catch(report)));
for (const id of ["obs-stream", "obs-record"]) bindClick(id, () => job({action:"obs",command:$(id).dataset.command}, () => {}));
bindForm("obs-scene", () => job({action:"obs",command:"scene",name:$("scene").value}, () => {}));
bindForm("obs-text", () => job({action:"obs",command:"text",name:$("source").value,text:$("source-text").value}));
bindForm("overlay-form", async () => {
  const values = formValues($("overlay-form")), rooms = {};
  for (const select of document.querySelectorAll("[data-overlay-room]"))
    if (document.querySelector(`[data-site="${select.dataset.overlayRoom}"]`).checked && select.value) rooms[select.dataset.overlayRoom] = select.value;
  await saveSettings(values);
  await job({action:"overlay", rooms}, async result => {
    $("overlay-url").value = result.url;
    try { await navigator.clipboard.writeText(result.url); alertMessage(t("Overlay URL copied.")); }
    catch { alertMessage(t("Copy the overlay URL from the box.")); }
  });
});
bindForm("analytics-form", async () => { await saveSettings(formValues($("analytics-form"))); await refreshAnalytics(); });
bindClick("export-csv", () => exportHotspots("csv"));
bindClick("export-edl", () => exportHotspots("edl"));
bindClick("event-rooms-reload", loadAnalysisRooms);
$("analytics-room").addEventListener("change", () => {
  clearRoomAnalysis();
  if ($("analytics-room").value) Promise.all([refreshAnalytics(), loadRoomEvents()]).catch(report);
});
bindClick("events-refresh", () => loadRoomEvents());
bindClick("events-older", () => eventCursor === null ? undefined : loadRoomEvents(true));
bindClick("events-export", async () => {
  const room = analysisRoom();
  const response = await fetch(`/api/room-events?room=${encodeURIComponent(room)}`,
    {headers:{"X-Dashboard-Token":token || ""}});
  if (!response.ok) throw new Error(t((await response.json()).error));
  const url = URL.createObjectURL(await response.blob()), link = node("a");
  link.href = url; link.download = "room-events.jsonl"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
bindClick("events-delete", async () => {
  const room = analysisRoom();
  if (await confirmAction(t("Permanently delete recorded events for {room}? Chat archives and other rooms are not affected.", {room}))) {
    await action({action:"delete_room_events", room});
    clearRoomAnalysis();
    await Promise.all([refreshAnalytics(), loadRoomEvents()]);
  }
});
function transcriptionConfiguration() {
  return {values:formValues($("translation-settings-form")), api_key:$("transcribe-api-key").value,
    clear_api_key:$("transcribe-clear-key").checked};
}
async function saveTranscriptionSettings(data = transcriptionConfiguration()) {
  await action({action:"transcription_settings", ...data});
  Object.assign(state.settings, data.values);
  state.transcription_api = {key_saved:!data.clear_api_key &&
    (!!data.api_key.trim() || !!state.transcription_api?.key_saved), error:""};
  if ($("transcribe-api-key").value === data.api_key) $("transcribe-api-key").value = "";
  if ($("transcribe-clear-key").checked === data.clear_api_key) $("transcribe-clear-key").checked = false;
  for (const message of [...state.messages, ...state.paid]) delete message.translation;
  lastChat = "";
  renderTranscript();
}
$("translation-settings-form").addEventListener("submit", event => event.preventDefault());
$("translation-settings-form").addEventListener("change", event => {
  if (!event.target.reportValidity()) return;
  const data = transcriptionConfiguration();
  queueSettingsSave(() => saveTranscriptionSettings(data)).catch(report);
});
bindClick("transcribe-detect-models", async () => {
  const data = transcriptionConfiguration();
  setTranscriptApiResult("Detecting models...");
  try {
    await job({action:"transcription_models", ...data}, result => {
      $("transcribe-models").replaceChildren(...result.models.map(model => new Option(model, model)));
      const input = $("translation-settings-form").elements.transcribe_api_model;
      if (input.value === data.values.transcribe_api_model && !result.models.includes(input.value))
        { input.value = result.models[0]; input.dispatchEvent(new Event("change", {bubbles:true})); }
      setTranscriptApiResult("Models found: {count}", {count:result.models.length});
    });
  } catch (error) { setTranscriptApiResult(error.message); throw error; }
});
bindClick("transcribe-test-api", async () => {
  setTranscriptApiResult("Testing translation...");
  try {
    await job({action:"transcription_test", ...transcriptionConfiguration()}, result => {
      setTranscriptApiResult("Translation successful: {text}", {text:result.text});
    });
  } catch (error) { setTranscriptApiResult(error.message); throw error; }
});
bindForm("transcribe-form", async () => {
  const data = transcriptionConfiguration();
  await queueSettingsSave(() => saveTranscriptionSettings(data));
  await action({action:"transcription",room:$("transcribe-room").value});
  transcriptCleared = 0;
});
bindClick("stop-transcribe", () => action({action:"transcription",command:"stop"}));
bindClick("clear-transcript", () => { transcriptCleared = state.transcription?.segments?.length || 0; renderTranscript(); });
bindClick("download-transcript", () => download($("transcript").textContent,"transcript.txt","text/plain;charset=utf-8"));
async function poll() {
  try { state = await api("/api/state"); connectionText = "Connected · independent room polling"; $("connection").textContent = t(connectionText); renderState(); }
  catch (error) { connectionText = ""; $("connection").textContent = error.message; }
  setTimeout(poll,1000);
}
async function start() {
  collectStaticText();
  try {
    const response = await fetch("/i18n.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    catalog = await response.json();
  } catch (error) { alertMessage(`Interface translations unavailable: ${error.message}`, true); }
  $("ui-language").replaceChildren(...Object.entries(catalog.languages).map(([code, name]) => new Option(name, code)));
  poll();
}
start();
