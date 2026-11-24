const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "html_dashboard", "dashboard.js"), "utf8");
const emoteFunctions = source.slice(source.indexOf("function insertText("), source.indexOf("function showEmotes("));
const jobFunctions = source.slice(source.indexOf("async function job("), source.indexOf("function report("));
const processJobs = source.slice(source.indexOf("function processJobs("), source.indexOf("function showSendResults("));

function fixture() {
  const input = {value:"draft ", selectionStart:6, selectionEnd:6, focus() { this.focused = true; }};
  const dialog = {open:true, close() { this.open = false; }};
  const requests = [], alerts = [];
  const context = vm.createContext({
    $:id => id === "emotes" ? dialog : input,
    state:{settings:{send_sites:[]}, jobs:{}},
    sites:["youtube", "bilibili", "missevan"],
    lastRooms:"old",
    observedJobs:new Set(),
    jobHandlers:new Map(),
    action:async data => { requests.push(data); return {job:"fixture"}; },
    saveSettings:async values => Object.assign(context.state.settings, values),
    alertMessage:(message, error) => alerts.push({message, error}),
    t:(text, values = {}) => text.replace("{name}", values.name || ""),
  });
  vm.runInContext(jobFunctions + emoteFunctions + processJobs, context);
  return {context, input, dialog, requests, alerts};
}

for (const site of ["bilibili", "missevan"]) {
  test(`${site} sends immediately and closes only after successful completion`, async () => {
    const f = fixture();
    await f.context.useEmote(site, {label:"Sticker", unique:"code", package_id:1, sticker_id:2});
    assert.equal(f.requests[0].action, "use_emote");
    assert.equal(f.requests[0].site, site);
    assert.equal(f.requests[0].sticker_id, 2);
    assert.equal(f.dialog.open, true);
    assert.equal(f.input.value, "draft ");
    f.context.state.jobs.fixture = {status:"done", result:{sent:site}};
    f.context.processJobs();
    assert.equal(f.dialog.open, false);
    assert.equal(f.alerts[0].message, "Sent Sticker");
  });

  test(`${site} leaves the picker open when sending fails`, async () => {
    const f = fixture();
    await f.context.useEmote(site, {label:"Sticker"});
    f.context.state.jobs.fixture = {status:"failed", error:"Send failed"};
    f.context.processJobs();
    assert.equal(f.dialog.open, true);
    assert.equal(f.alerts[0].error, true);
    assert.equal(f.alerts[0].message, "Send failed");
  });

  test(`${site} leaves the picker open if submitting the send fails`, async () => {
    const f = fixture();
    f.context.action = async () => { throw new Error("Connection failed"); };
    await assert.rejects(f.context.useEmote(site, {label:"Sticker"}), /Connection failed/);
    assert.equal(f.dialog.open, true);
    assert.equal(f.input.value, "draft ");
  });
}

test("YouTube inserts multiple emotes into the draft without sending or closing", async () => {
  const f = fixture();
  await f.context.useEmote("youtube", {code:":wave:", label:"Wave"});
  await f.context.useEmote("youtube", {code:":heart:", label:"Heart"});
  assert.equal(f.input.value, "draft :wave::heart:");
  assert.equal(f.dialog.open, true);
  assert.equal(f.requests.length, 0);
  assert.equal(f.context.state.settings.send_sites.includes("youtube"), true);
});

test("MissEvan kaomoji replaces the selection, closes and focuses the draft without sending", async () => {
  const f = fixture();
  f.input.selectionStart = 0;
  f.input.selectionEnd = 5;
  await f.context.useEmote("kaomoji", {value:"(^_^)", label:"Smile"});
  assert.equal(f.input.value, "(^_^) ");
  assert.equal(f.input.focused, true);
  assert.equal(f.dialog.open, false);
  assert.equal(f.requests.length, 0);
});

test("emote picker previews the hovered or focused emote larger without sending", () => {
  const preview = source.slice(source.indexOf("function previewEmote("), source.indexOf("async function loadEmotes("));
  const children = [];
  const box = {replaceChildren(...items) { children.splice(0, children.length, ...items); }};
  const context = vm.createContext({
    $:() => box,
    image:(src, cls, alt) => ({src, cls, alt}),
    node:(tag, text) => ({tag, text}),
  });
  vm.runInContext(preview.slice(0, preview.indexOf("function showEmotes(")), context);
  context.previewEmote({image:"https://i0.hdslb.com/a.png", label:"Wave"});
  assert.equal(children[0].cls, "emote-large");
  assert.equal(children[1].text, "Wave");
  context.clearEmotePreview();
  assert.equal(children.length, 0);
  assert.match(preview, /"mouseenter", "focus"/);
  assert.match(preview, /"mouseleave", "blur"/);
});

test("Hide gifts removes gifts from the comment feed only", () => {
  const start = source.indexOf("function renderChat(");
  const render = source.slice(start, source.indexOf("function speechStatus(", start));
  const feeds = {};
  const gift = {type:"gift", id:1}, comment = {type:"chat", id:2}, paid = [gift];
  const context = vm.createContext({
    state:{messages:[gift, comment], joins:[], paid, settings:{hide_gifts:true}},
    lastChat:"",
    window:{getSelection:() => ""},
    document:{createTextNode:text => text},
    $:id => id,
    node:() => ({append() {}}),
    t:text => text,
    appendReadings() {},
    messageRow:message => message,
    fillFeed:(id, rows) => { feeds[id] = rows; },
  });
  vm.runInContext(render, context);
  context.renderChat();
  assert.deepEqual(feeds["chat-feed"].map(row => row.id), [2]);
  assert.deepEqual(feeds["paid-feed"].map(row => row.id), [1]);
  context.state.settings.hide_gifts = false;
  context.renderChat();
  assert.deepEqual(feeds["chat-feed"].map(row => row.id), [1, 2]);
});
