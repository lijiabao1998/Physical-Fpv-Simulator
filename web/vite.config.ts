import { defineConfig } from 'vite';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
const sha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
const dirty = execFileSync('git', ['status', '--porcelain', '--untracked-files=normal'], { encoding: 'utf8' }).trim().length > 0;
const version = '0.1.0', base = '/fpv/';
export default defineConfig({
  base,
  define: { __BUILD_SHA__: JSON.stringify(sha), __VERSION__: JSON.stringify(version) },
  plugins: [{name:'build-provenance', generateBundle() {
    this.emitFile({type:'asset',fileName:'THIRD_PARTY_LICENSES.txt',source:['three/LICENSE','@dimforge/rapier3d-compat/LICENSE'].map(path=>`=== ${path} ===\n${readFileSync(`node_modules/${path}`,'utf8')}`).join('\n\n')});
    this.emitFile({type:'asset',fileName:'version.json',source:JSON.stringify({version,commit:sha,dirty,base,builtAt:new Date().toISOString()},null,2)});
  }}],
  build: { target: 'es2022', chunkSizeWarningLimit: 3000 },
});
