const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "html_dashboard", "dashboard.js"), "utf8");
const save = source.slice(source.indexOf("async function saveSettings("),
  source.indexOf("// ── Chat rooms"));

function tab() {
  const stored = new Map(), actions = [];
  const context = vm.createContext({
    tabView:{selected_rooms:{bilibili:"bilibili:1"}, visible_sites:["bilibili"], send_sites:["bilibili"]},
    state:{settings:{}}, lastSpeech:0, lastChat:"old", lastRooms:"old",
    sessionStorage:{setItem:(key, value) => stored.set(key, value)},
    action:async data => actions.push(data),
    api:async () => ({settings:{}, speech_cursor:12}),
    clearSpeech:() => {}, renderState:() => {},
  });
  vm.runInContext(save, context);
  return {context, stored, actions};
}

test("room, visibility and send choices stay in each tab and never change shared settings", async () => {
  const first = tab(), second = tab();
  await first.context.saveSettings({selected_rooms:{bilibili:"bilibili:2"},
    visible_sites:["youtube"], send_sites:["youtube"]});
  assert.equal(first.context.tabView.selected_rooms.bilibili, "bilibili:2");
  assert.equal(second.context.tabView.selected_rooms.bilibili, "bilibili:1");
  assert.equal(first.actions.length, 0);
  assert.equal(first.context.lastSpeech, 12);
  assert.equal(JSON.parse(first.stored.get("dashboard-view")).send_sites[0], "youtube");
  assert.equal(second.stored.size, 0);
});

test("translation and other shared settings still use backend settings action", async () => {
  const f = tab();
  await f.context.saveSettings({translate_enabled:true});
  assert.equal(f.actions.length, 1);
  assert.equal(f.actions[0].action, "settings");
  assert.equal(f.context.state.settings.translate_enabled, true);
  assert.equal(f.stored.size, 0);
});

test("API calls attach a snapshot of the tab view for polling, sends and emotes", async () => {
  const calls = [];
  const context = vm.createContext({
    tabView:{selected_rooms:{youtube:"youtube:日本語"}},
    fetch:async (url, options) => {
      calls.push({url, options});
      return {ok:true, json:async () => ({ok:true})};
    },
  });
  vm.runInContext(source.slice(source.indexOf("async function api("), source.indexOf("async function action(")), context);
  for (const action of ["send", "emotes", "use_emote"])
    await context.api("/api/action", {action});
  await context.api("/api/state");
  for (const {options} of calls) {
    assert.equal("X-Dashboard-Token" in options.headers, false);
    const view = JSON.parse(decodeURIComponent(options.headers["X-Dashboard-View"]));
    assert.equal(view.selected_rooms.youtube, "youtube:日本語");
  }
});

test("dashboard startup and event exports do not require a launch token", () => {
  assert.equal(source.includes("dashboard-token"), false);
  assert.equal(source.includes("X-Dashboard-Token"), false);
});
