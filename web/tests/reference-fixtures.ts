import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import baseline from '../../reference/fixtures.json';

// Frozen evidence stays immutable. Re-executed Python results are independently
// subjected to the same physical tolerances rather than overwriting that evidence.
const path=fileURLToPath(new URL('../numerical-results/python-fixtures.json',import.meta.url));
if(process.env.CI&&!existsSync(path))throw new Error('CI requires freshly generated Python reference');
const fresh=existsSync(path)?JSON.parse(readFileSync(path,'utf8')) as typeof baseline:null;
if(fresh&&(fresh.schema!==baseline.schema||fresh.source_sha!==baseline.source_sha||fresh.cases.length!==baseline.cases.length))throw new Error('Regenerated reference provenance mismatch');
export default {...baseline,cases:[...baseline.cases,...(fresh?.cases.map(c=>({...c,evidenceSource:'regenerated'}))??[])]};
