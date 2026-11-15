const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "assets", "html_dashboard", "dashboard.js"), "utf8");
const start = source.indexOf("let authorHistory = null;");
const end = source.indexOf("\nfunction ", source.indexOf("async function loadAuthorHistory(") + 1);

function fixture(action) {
  const elements = {};
  function node(tag, text = "") {
    return {tag, textContent:text, children:[], append(...items) { this.children.push(...items); },
      replaceChildren() { this.children = []; }, showModal() { this.open = true; }};
  }
  const $ = id => elements[id] ||= node("div");
  const context = vm.createContext({$, node, action, t:text => text});
  vm.runInContext(source.slice(start, end), context);
  return {context, $};
}

test("clicking an author opens room-scoped history and loads older messages", async () => {
  const calls = [];
  const f = fixture(async data => {
    calls.push(data);
    return {events:[{received_at:1700000000, payload:{author:"Viewer", text:"<script>plain text</script>"}}],
      next:calls.length === 1 ? 12 : null};
  });
  await f.context.showAuthorHistory({_monitor_id:"youtube:room", author_id:"42", author:"Viewer"});
  assert.equal(f.$("author-history").open, true);
  assert.equal(calls[0].room, "youtube:room");
  assert.equal(calls[0].author_id, "42");
  assert.equal(f.$("author-history-rows").children.length, 1);
  assert.equal(f.$("author-history-rows").children[0].children[1].textContent,
    "Viewer: <script>plain text</script>");
  await f.context.loadAuthorHistory();
  assert.equal(calls[1].before, 12);
  assert.equal(f.$("author-history-rows").children.length, 2);
  assert.equal(f.$("author-history-older").disabled, true);
});

test("history errors are visible and leave pagination retryable", async () => {
  const f = fixture(async () => { throw new Error("Read failed"); });
  await assert.rejects(f.context.showAuthorHistory({
    _monitor_id:"bilibili:1", author:"Viewer",
  }), /Read failed/);
  assert.equal(f.$("author-history-status").textContent, "Read failed");
  assert.equal(f.$("author-history-older").disabled, false);
});

test("empty history shows an explicit message", async () => {
  const f = fixture(async () => ({events:[], next:null}));
  await f.context.showAuthorHistory({_monitor_id:"bilibili:1", author:"Viewer"});
  assert.equal(f.$("author-history-status").textContent, "No messages yet.");
  assert.equal(f.$("author-history-older").disabled, true);
});
