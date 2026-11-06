const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "html_dashboard", "dashboard.js"), "utf8");
const context = vm.createContext({
  t:(text, values = {}) => text.replace("{name}", values.name || ""),
});
vm.runInContext(source.slice(source.indexOf("function liveNotificationText("),
  source.indexOf("function showLiveNotification(")), context);

test("native and custom notification text uses current backend fields", () => {
  const text = context.liveNotificationText({channel:"Creator", detail:"Tonight's stream", platform:"YouTube"});
  assert.equal(text.heading, "Creator is live");
  assert.equal(text.body, "Tonight's stream");
});

test("old notification fields remain compatible", () => {
  const text = context.liveNotificationText({name:"Creator", title:"Old stream title"});
  assert.equal(text.heading, "Creator is live");
  assert.equal(text.body, "Old stream title");
});

test("missing channel details never produce undefined", () => {
  for (const notice of [{room:"bilibili:123"}, {platform:"YouTube"}, {}]) {
    const text = context.liveNotificationText(notice);
    assert.equal(text.heading.includes("undefined"), false);
    assert.equal(text.body, "");
    assert.ok(text.name);
  }
});

test("native browser notifications use the shared heading and body", () => {
  const start = source.indexOf("const {heading, body} = liveNotificationText(notice);");
  const end = source.indexOf("lastNotice = notice.id;", start);
  assert.ok(start >= 0 && end > start);
  const calls = [];
  const nativeContext = vm.createContext({
    notice:{channel:"Creator", detail:"Live title"},
    liveNotificationText:context.liveNotificationText,
    alertMessage:text => calls.push(text),
    window:{Notification:true},
    Notification:class {
      static permission = "granted";
      constructor(heading, options) { calls.push({heading, body:options.body}); }
    },
    showLiveNotification:() => {},
  });
  vm.runInContext(source.slice(start, end), nativeContext);
  assert.equal(calls[0], "Creator is live · Live title");
  assert.equal(calls[1].heading, "Creator is live");
  assert.equal(calls[1].body, "Live title");
});
