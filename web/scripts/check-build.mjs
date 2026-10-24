import { readFile, stat, readdir } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import assert from 'node:assert/strict';
const root = resolve('dist');
const base = '/Physical-Fpv-Simulator/';
const html = await readFile(resolve(root, 'index.html'), 'utf8');
assert.match(html, /<canvas|type="module"/, 'Application entry missing');
const references = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)].map(m => m[1]);
let checked = 0;
for (const url of references) {
  if (/^(?:https?:|data:|#)/.test(url)) continue;
  assert.ok(url.startsWith(base), `Asset not rooted at GitHub Pages base: ${url}`);
  const path = resolve(root, decodeURIComponent(url.slice(base.length).split(/[?#]/)[0]));
  assert.ok(!relative(root, path).startsWith('..'), 'Asset escapes build root');
  assert.ok((await stat(path)).isFile(), `Missing asset: ${url}`); checked++;
}
assert.ok(checked > 0, 'No local assets verified');
const version = JSON.parse(await readFile(resolve(root, 'version.json'), 'utf8'));
assert.match(version.commit, /^[0-9a-f]{40}$/);
assert.equal(version.version, '0.1.0');
assert.equal(version.base, base);
if (process.env.CI) assert.equal(version.dirty, false, 'CI release must use a clean source tree');
const assets = await readdir(resolve(root, 'assets'));
assert.ok(assets.some(n => n.endsWith('.js')), 'JavaScript bundle missing');
console.log(JSON.stringify({check:'static-build', status:'PASS', checked, version, assets}, null, 2));
