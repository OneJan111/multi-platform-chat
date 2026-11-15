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

test("monitor cards drop before or after a target and persist the new order", async () => {
  const calls = [];
  let actionCompleted;
  const actionResult = new Promise(resolve => { actionCompleted = resolve; });
  const orderContext = vm.createContext({
    state:{targets:[{id:"one"}, {id:"two"}, {id:"three"}]},
    action:async data => { calls.push(data); return actionResult; },
    lastMonitor:"unchanged", renderMonitor:() => {},
  });
  vm.runInContext(source.slice(source.indexOf("function reorderMonitorRoom("),
    source.indexOf("function renderMonitor(")), orderContext);
  const reordered = orderContext.reorderMonitorRoom("one", "three", true);
  assert.deepEqual([...calls[0].rooms], ["two", "three", "one"]);
  actionCompleted({ok:true});
  await reordered;
  assert.deepEqual(orderContext.state.targets.map(room => room.id), ["two", "three", "one"]);
});
vm.runInContext(functions, context);

test("monitor cards expose a drag handle and drop on the target card", async () => {
  const calls = [], elements = [];
  const element = () => {
    const listeners = {};
    const result = {
      children:[], listeners, classList:{add(){}, remove(){}},
      append(...children) { this.children.push(...children); },
      addEventListener(type, callback) { listeners[type] = callback; },
      setAttribute(){}, contains(){return false;}, getBoundingClientRect(){return {top:0};},
      offsetHeight:100,
    };
    elements.push(result);
    return result;
  };
  const monitorCards = {children:[], replaceChildren() { this.children = []; }, append(card) { this.children.push(card); }};
  let pendingAction;
  const renderContext = vm.createContext({
    state:{
      targets:[{id:"one", platform:"youtube", target:"one"},
        {id:"two", platform:"bilibili", target:"two"},
        {id:"three", platform:"missevan", target:"three"}],
      statuses:{}, recording:{}, record_armed:[], bilibili_gift_revenue:{},
    },
    lastMonitor:"",
    labels:{youtube:"YouTube", bilibili:"Bilibili", missevan:"MissEvan"},
    t:text => text, $:id => id === "monitor-cards" ? monitorCards : element(),
    node:(_tag, text, className) => {
      const result = element(); result.textContent = text; result.className = className; return result;
    },
    document:{createTextNode:() => element()},
    button:(text, callback) => ({text, callback}),
    checkbox:() => element(),
    job:async () => {}, action:data => {
      calls.push(data);
      return new Promise(resolve => { pendingAction = resolve; });
    },
    report:() => {},
    monitorTooltip:() => "",
  });
  vm.runInContext(source.slice(source.indexOf("function reorderMonitorRoom("),
    source.indexOf("function monitorTooltip(")), renderContext);
  renderContext.renderMonitor();
  const [first, , third] = monitorCards.children;
  const handle = first.children[0].children[0];
  assert.equal(handle.draggable, true);
  let draggedId = "";
  handle.listeners.dragstart({dataTransfer:{setData(_type, value){draggedId = value;}, effectAllowed:""}});
  const drop = third.listeners.drop({
    preventDefault(){}, clientY:75,
    dataTransfer:{getData:() => draggedId},
  });
  assert.equal(drop, undefined);
  assert.deepEqual(calls[0].rooms, ["two", "three", "one"]);
  pendingAction({ok:true});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(renderContext.state.targets.map(room => room.id), ["two", "three", "one"]);
});

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
