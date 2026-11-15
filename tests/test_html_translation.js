const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const {test} = require("node:test");
const vm = require("node:vm");

const assets = join(__dirname, "..", "assets", "html_dashboard");
const html = readFileSync(join(assets, "index.html"), "utf8");
const source = readFileSync(join(assets, "dashboard.js"), "utf8");

test("all translation controls appear once in the dedicated translation tab", () => {
  const panel = html.match(/<section id="translation"[\s\S]*?<\/section>/)[0];
  assert.match(html, /data-tab="translation"/);
  for (const name of [
    "translate_enabled", "translate_target", "tts_translate", "overlay_translate",
    "transcribe_translate", "transcribe_target_language", "transcribe_provider",
    "transcribe_api_base", "transcribe_api_model", "transcribe_background",
    "transcribe_glossary", "transcribe_context_sentences",
    "transcribe_reasoning_effort",
  ]) {
    assert.equal(html.split(`name="${name}"`).length - 1, 1, name);
    assert.ok(panel.includes(`name="${name}"`), name);
  }
  for (const id of ["transcribe-api-key", "transcribe-clear-key",
    "transcribe-detect-models", "transcribe-test-api"])
    assert.ok(panel.includes(`id="${id}"`), id);
});

test("speech recognition stays in its own autosaved form", () => {
  const panel = html.match(/<section id="transcription"[\s\S]*?<\/section>/)[0];
  assert.match(panel, /id="recognition-settings-form"[^>]*data-settings data-autosave/);
  for (const name of ["transcribe_model", "transcribe_source_language", "transcribe_models_path"])
    assert.ok(panel.includes(`name="${name}"`), name);
  assert.match(panel, /id="transcribe-form"/);
  assert.match(html, /id="translation-preferences-form"[^>]*data-settings data-autosave/);
});

test("API save, model detection and translation testing read the relocated form", () => {
  const form = {values:{transcribe_provider:"openai_compatible",
    transcribe_api_base:"http://localhost:1234/v1", transcribe_api_model:"fixture-model",
    transcribe_translate:true, transcribe_target_language:"ja"}};
  const controls = {
    "translation-settings-form":form,
    "transcribe-api-key":{value:"fixture-key"},
    "transcribe-clear-key":{checked:false},
  };
  const context = vm.createContext({$:id => controls[id], formValues:element => element.values});
  vm.runInContext(source.slice(source.indexOf("function transcriptionConfiguration("),
    source.indexOf("async function saveTranscriptionSettings(")), context);
  const result = context.transcriptionConfiguration(true);
  assert.equal(result.values.transcribe_provider, "openai_compatible");
  assert.equal(result.api_key, "fixture-key");
  assert.equal(result.clear_api_key, false);
  const autosave = context.transcriptionConfiguration();
  assert.equal("transcribe_provider" in autosave.values, false);
  assert.equal(form.values.transcribe_provider, "openai_compatible");
  assert.equal(autosave.values.transcribe_api_model, "fixture-model");
  assert.equal(source.includes('$("transcription-settings-form")'), false);
});

test("service switching is explicit and Google is selectable independently of environment", () => {
  assert.match(html, /option value="google">Google Translate/);
  assert.match(html, /id="apply-translation-provider"/);
  assert.match(source, /event\.target\.id === "transcribe-provider"/);
  assert.match(source, /bindClick\("apply-translation-provider"[\s\S]*?transcriptionConfiguration\(true\)/);
});

test("changing the service does not save until apply is clicked", async () => {
  const listeners = {}, clicks = {}, saves = [];
  const form = {addEventListener:(name, callback) => { listeners[name] = callback; }};
  const context = vm.createContext({
    $:() => form,
    renderTranslationProvider:() => {},
    transcriptionConfiguration:includeProvider => ({
      values:includeProvider ? {transcribe_provider:"google"} : {transcribe_target_language:"ja"},
    }),
    queueSettingsSave:async callback => callback(),
    saveTranscriptionSettings:async data => saves.push(data),
    bindClick:(id, callback) => { clicks[id] = callback; },
    report:error => { throw error; },
  });
  const start = source.indexOf('$("translation-settings-form").addEventListener("submit"');
  const end = source.indexOf('bindClick("transcribe-detect-models"', start);
  vm.runInContext(source.slice(start, end), context);
  listeners.change({target:{id:"transcribe-provider"}});
  assert.equal(saves.length, 0);
  listeners.change({target:{id:"other", reportValidity:() => true}});
  await Promise.resolve();
  assert.equal("transcribe_provider" in saves[0].values, false);
  await clicks["apply-translation-provider"]();
  assert.equal(saves[1].values.transcribe_provider, "google");
});
