import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import process from 'node:process';
import test from 'node:test';

const require = createRequire(import.meta.url);
const eslintRequire = createRequire(require.resolve('eslint'));
const minimatchRequire = createRequire(eslintRequire.resolve('minimatch'));
const expansionPath = minimatchRequire.resolve('brace-expansion');

test('ESLint brace expansion bounds malformed rewrite work', () => {
  const result = spawnSync(process.execPath, ['-e', `
    const expand = require(${JSON.stringify(expansionPath)});
    for (const n of [32000, 64000]) {
      const output = expand('{a}' + '}'.repeat(n) + ',z}');
      if (!Array.isArray(output) || output.length === 0) process.exit(1);
    }
  `], { timeout: 2000, encoding: 'utf8' });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});

test('ESLint brace expansion preserves ordinary lists and ranges', () => {
  const expand = minimatchRequire('brace-expansion');
  assert.deepEqual(expand('file{a,b}.js'), ['filea.js', 'fileb.js']);
  assert.deepEqual(expand('{1..3}'), ['1', '2', '3']);
  assert.deepEqual(expand('plain.js'), ['plain.js']);
});
