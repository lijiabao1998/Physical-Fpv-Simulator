/* Mocked DOM/Gamepad regression checks against the actual embedded UI script.
 * These checks do not launch a browser or validate any physical controller.
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(
  path.join(__dirname, '../src/physical_fpv/fpv/web/index.html'), 'utf8',
);
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, 'The UI must contain its executable script');
// Do not start the network-driven loop; each test explicitly advances tick().
const startup = "fetch('/state')";
const startupAt = match[1].lastIndexOf(startup);
assert.ok(startupAt >= 0, 'Locate and suppress only the startup state fetch');
const script = match[1].slice(0, startupAt);

function fixture() {
  const elements = new Map();
  const events = new Map();
  const requests = [];
  const timers = [];
  const exports = [];
  const createdElements = [];
  const controls = new Set(['throttle', 'roll', 'pitch', 'yaw']);
  let pads = [];
  let response = async (_route, body) => ({ controls: body.controls ?? {} });
  let fetchResponse = async () => { throw Error('Unexpected mocked network call'); };

  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        value: 0,
        min: id === 'throttle' ? 0 : -1,
        max: 1,
        tagName: controls.has(id) ? 'INPUT' : 'BUTTON',
        textContent: '',
        style: {},
        className: '',
        getContext() { return {}; },
        click() { return this.onclick?.(); },
      });
    }
    return elements.get(id);
  }

  function listen(name, handler) {
    if (!events.has(name)) events.set(name, []);
    events.get(name).push(handler);
  }

  const sandbox = {
    document: {
      getElementById: element, addEventListener: listen, hidden: false,
      createElement(tag) {
        const created = { tagName: tag.toUpperCase(), clicks: 0, click() { this.clicks++; } };
        createdElements.push(created);
        return created;
      },
    },
    window: { addEventListener: listen },
    navigator: { getGamepads: () => pads },
    performance: { now: () => 0 },
    setTimeout: (handler, delay) => { timers.push({ handler, delay }); },
    fetch: (...args) => fetchResponse(...args),
    Blob: class {
      constructor(parts, options) { this.parts = parts; this.options = options; }
    },
    URL: {
      createObjectURL(blob) { exports.push(blob); return 'blob:mock-replay'; },
      revokeObjectURL() {},
    },
    console,
    __request: async (route, body) => {
      requests.push({ route, body: JSON.parse(JSON.stringify(body)) });
      return response(route, body);
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(script, context, { filename: 'fpv-ui-actual-script.js' });
  // Rendering is outside this logic-only test. All input and tick code is original.
  vm.runInContext(
    'render=()=>{};update=()=>{window.fpvTelemetry=state};request=__request;', context,
  );

  return {
    requests,
    timers,
    exports,
    createdElements,
    element,
    evaluate: source => vm.runInContext(source, context),
    tick: () => vm.runInContext('tick()', context),
    setPads: value => { pads = value; },
    setResponse: handler => { response = handler; },
    setFetchResponse: handler => { fetchResponse = handler; },
    emit: (name, event = {}) => {
      for (const handler of events.get(name) ?? []) handler(event);
    },
  };
}

const pad = (buttonPressed = false, horizontal = 0) => ({
  id: 'Mock standard controller: no hardware validation',
  axes: [horizontal, 0, 0, 1],
  buttons: [{ pressed: false }, { pressed: buttonPressed }],
});

const cases = [
  ['keyboard and gamepad roll signs match x-forward/y-left/z-up', async () => {
    const f = fixture();
    assert.equal(f.evaluate("keys.add('a');controls().roll"), -1);
    assert.equal(f.evaluate("keys.clear();keys.add('d');controls().roll"), 1);
    f.evaluate('keys.clear()');
    f.setPads([pad(false, 0.7)]);
    assert.equal(f.evaluate('controls().roll'), 0.7);
  }],
  ['Space disarms even when a range slider has focus', async () => {
    const f = fixture();
    f.evaluate('arm(true);setAxis("throttle",.6)');
    let prevented = false;
    f.emit('keydown', {
      target: f.element('throttle'), key: ' ', repeat: false,
      preventDefault() { prevented = true; },
    });
    assert.equal(f.evaluate('armed'), false);
    assert.equal(+f.element('throttle').value, 0);
    assert.equal(prevented, true);
  }],
  ['repeated reset requests queue while a step is in flight', async () => {
    const f = fixture();
    let release;
    f.setResponse((route, body) => route === '/step'
      ? new Promise(resolve => { release = resolve; })
      : Promise.resolve({ controls: { armed: false }, reset: true }));
    const pending = f.tick();
    assert.equal(f.evaluate('busy'), true);
    f.element('reset').click();
    f.element('reset').click();
    assert.equal(f.evaluate('resetRequested'), true);
    release({ controls: { armed: false } });
    await pending;
    await f.tick();
    assert.deepEqual(f.requests.map(r => r.route), ['/step', '/reset']);
    assert.equal(f.evaluate('resetRequested'), false);
    assert.equal(f.evaluate('armed'), false);
    assert.equal(f.evaluate('paused'), false);
  }],
  ['paused arm/disarm emits zero-duration events and then stays idle', async () => {
    const f = fixture();
    f.evaluate('paused=true;arm(true);setAxis("throttle",.5)');
    await f.tick();
    assert.equal(f.requests[0].body.duration_s, 0);
    assert.equal(f.requests[0].body.controls.armed, true);
    f.evaluate('arm(false)');
    await f.tick();
    assert.equal(f.requests[1].body.duration_s, 0);
    assert.equal(f.requests[1].body.controls.armed, false);
    assert.equal(f.requests[1].body.controls.throttle, 0);
    await f.tick();
    await f.tick();
    assert.equal(f.requests.length, 2);
  }],
  ['held gamepad disarm button cannot generate a paused request loop', async () => {
    const f = fixture();
    f.setPads([pad(true)]);
    f.evaluate('paused=true;arm(false)');
    for (let i = 0; i < 4; i++) await f.tick();
    assert.equal(f.requests.length, 1);
    assert.equal(f.requests[0].body.duration_s, 0);
    assert.equal(f.evaluate('controlsDirty'), false);
  }],
  ['persistent server errors pause rather than retry indefinitely', async () => {
    const f = fixture();
    f.setResponse(async () => { throw Error('Mock persistent rejection'); });
    f.evaluate('arm(true)');
    for (let i = 0; i < 4; i++) await f.tick();
    assert.equal(f.requests.length, 1);
    assert.equal(f.evaluate('paused'), true);
    assert.equal(f.evaluate('armed'), false);
    assert.equal(f.element('error').textContent, 'Mock persistent rejection');
  }],
  ['paused gamepad disconnect clears commands and synchronizes disarm', async () => {
    const f = fixture();
    const connected = pad();
    f.setPads([connected]);
    f.evaluate('paused=true;arm(true)');
    await f.tick();
    assert.equal(f.evaluate('gamepadWasConnected'), true);
    f.setPads([]);
    f.emit('gamepaddisconnected', { gamepad: connected });
    assert.equal(f.evaluate('armed'), false);
    await f.tick();
    const last = f.requests.at(-1);
    assert.equal(last.body.duration_s, 0);
    assert.deepEqual(last.body.controls, {
      armed: false, throttle: 0, roll: 0, pitch: 0, yaw: 0,
    });
    await f.tick();
    assert.equal(f.requests.length, 2);
  }],
  ['replay export preserves server JSON bytes and numeric representation', async () => {
    const f = fixture();
    const raw = '{"zero":0.0,"negative":-0.0,"exponent":1e-07,"sha256":"mock"}\n';
    f.setFetchResponse(async route => {
      assert.equal(route, '/replay');
      return {
        text: async () => raw,
        json: async () => { throw Error('Replay bytes must not be parsed and reserialized'); },
      };
    });
    await f.element('export').click();
    assert.equal(f.exports.length, 1);
    assert.equal(f.exports[0].parts.join(''), raw);
    const download = f.createdElements.at(-1);
    assert.equal(download.download, 'fpv-control-replay.json');
    assert.equal(download.clicks, 1);
  }],
];

(async () => {
  for (const [name, check] of cases) {
    await check();
    console.log(`PASS: ${name}`);
  }
  console.log(`${cases.length} mocked DOM/Gamepad checks passed; browser/hardware NOT RUN.`);
})().catch(error => {
  console.error(error.stack ?? error);
  process.exitCode = 1;
});
