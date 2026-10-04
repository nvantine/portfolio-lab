// DOM and network doubles exercise polling without browser dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const region = {
  dataset: {liveRegion: "datasets"}, detail: {id: "coverage-1", open: true}, checkbox: {id: "accept-1", type: "checkbox", checked: true},
  get innerHTML() { return this.html; },
  set innerHTML(value) { this.html = value; this.detail.open = false; this.checkbox.checked = false; },
  querySelectorAll(selector) {
    if (selector.startsWith("details")) return [this.detail];
    if (selector.startsWith("input")) return [this.checkbox];
    return [];
  },
};
const select = {id: "id_dataset", value: "3", options: [{value: "3"}, {value: "4"}]};
const draft = {value: "My unsaved hypothesis"};
const feedback = {};
const root = {dataset: {liveStatus: "/activity/status/?scope=datasets", liveRevision: "initial"}};
const incoming = {
  querySelector(selector) {
    if (selector === "[data-live-status]") return {dataset: {liveRevision: "rendered-latest"}};
    return {innerHTML: "Finished preview"};
  },
  getElementById: () => ({innerHTML: "New dataset choices"}),
};
const timers = [];
const calls = [];
let replies = [];
const document = {
  hidden: false, activeElement: null, addEventListener() {},
  querySelector: () => feedback,
  querySelectorAll(selector) {
    if (selector === "[data-live-region]") return [region];
    if (selector === "select[data-live-options]") return [select];
    return [];
  },
};
const context = vm.createContext({
  document, window: {location: {href: "http://localhost/datasets/"}},
  DOMParser: class { parseFromString() { return incoming; } },
  fetch: async (url, options) => {
    calls.push({url, options});
    const reply = replies.shift();
    if (reply instanceof Error) throw reply;
    return reply;
  },
  setTimeout(callback, delay) { timers.push({callback, delay}); },
});
vm.runInContext(fs.readFileSync("portfolio/static/portfolio/live.js", "utf8"), context);
const ok = revision => ({ok: true, json: async () => ({revision, worker: {available: true}})});
const flush = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  // A network interruption retries rather than permanently stopping updates.
  replies = [new Error("Offline")];
  context.startLivePage(root);
  await flush();
  assert.match(feedback.textContent, /Retrying automatically/);
  assert.equal(timers.length, 1);
  assert.equal(timers[0].delay, 2000);
  // Unchanged revisions don't download an entire page.
  replies = [ok("initial")];
  await timers.shift().callback();
  assert.equal(calls.length, 2);
  assert.match(feedback.textContent, /Up to date/);
  // Changed revisions use GET and update lists, keeping drafts/selections.
  replies = [ok("finished"), {ok: true, text: async () => "Rendered page"}];
  await timers.shift().callback();
  assert.equal(region.html, "Finished preview");
  assert.equal(region.detail.open, true);
  assert.equal(region.checkbox.checked, true);
  assert.equal(select.value, "3");
  assert.equal(draft.value, "My unsaved hypothesis");
  assert.equal(root.dataset.liveRevision, "rendered-latest");
  assert.ok(calls.every(call => call.options.cache === "no-store" && !call.options.method));
  // Updates defer while a user is interacting with a list control.
  document.activeElement = {closest: () => region};
  const previousCalls = calls.length;
  replies = [ok("changed-again")];
  await timers.shift().callback();
  assert.equal(calls.length, previousCalls + 1);
  assert.equal(root.dataset.liveRevision, "rendered-latest");
  // Login redirects don't replace application content with a login page.
  document.activeElement = null;
  replies = [{ok: true, redirected: true}];
  await timers.shift().callback();
  assert.match(feedback.textContent, /Retrying/);
  assert.equal(root.dataset.liveRevision, "rendered-latest");
  // Hidden tabs retain a retry schedule while avoiding network traffic.
  document.hidden = true;
  const hiddenCalls = calls.length;
  await timers.shift().callback();
  assert.equal(calls.length, hiddenCalls);
  assert.equal(timers.length, 1);
  console.log("Live page polling checks passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
