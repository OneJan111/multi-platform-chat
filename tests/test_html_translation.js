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
  const result = context.transcriptionConfiguration();
  assert.equal(result.values, form.values);
  assert.equal(result.api_key, "fixture-key");
  assert.equal(result.clear_api_key, false);
  assert.equal(source.includes('$("transcription-settings-form")'), false);
});
