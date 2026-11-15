const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "html_dashboard", "dashboard.js"), "utf8");
const context = vm.createContext({t:text => text});
vm.runInContext(source.slice(source.indexOf("function flags("), source.indexOf("function copyText(")), context);

test("membership duration remains visible even when the member has a badge icon", () => {
  for (const membership_icon of ["", "https://yt3.ggpht.com/badge"]) {
    const flags = context.flags({platform:"youtube", membership:"Member (6 months)", membership_icon});
    assert.ok(flags.includes("Member (6 months)"));
  }
});

test("non-members do not gain a membership label", () => {
  assert.equal(context.flags({platform:"youtube"}).length, 0);
});
