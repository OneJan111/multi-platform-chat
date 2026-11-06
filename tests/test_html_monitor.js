const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "html_dashboard", "dashboard.js"), "utf8");
const functions = source.slice(source.indexOf("function monitorTooltip("), source.indexOf("function renderLogins("));
const context = vm.createContext({
  t:(text, values = {}) => text.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? ""),
});
vm.runInContext(functions, context);

test("Bilibili tooltip includes audience, session revenue, and combined zone", () => {
  const tooltip = context.monitorTooltip(
    {platform:"bilibili", target:"123"},
    {viewers:120, room_audience:115, popularity:5000, parent_area_name:"Games", area_name:"RPG"},
    "¥25",
  );
  assert.match(tooltip, /115/);
  assert.match(tooltip, /¥25/);
  assert.match(tooltip, /Games \/ RPG/);
});

test("MissEvan tooltip includes viewer count and API revenue", () => {
  const tooltip = context.monitorTooltip(
    {platform:"missevan", target:"456"},
    {viewers:30, attention_count:100, revenue:12},
  );
  assert.match(tooltip, /30 viewers/);
  assert.match(tooltip, /Revenue: 12/);
});
