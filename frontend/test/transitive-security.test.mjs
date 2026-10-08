import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import process from 'node:process';
import test from 'node:test';

// pnpm test runs in each install surface; exercise that surface's graph.
const require = createRequire(resolve(process.cwd(), 'package.json'));
const tailwindRequire = createRequire(require.resolve('tailwindcss'));
const postcssRequire = createRequire(tailwindRequire.resolve('postcss'));
const selectorPath = tailwindRequire.resolve('postcss-selector-parser');
const sourceMapPath = postcssRequire.resolve('source-map-js');

test('Tailwind selector parsing bounds flat-selector work', () => {
  const result = spawnSync(process.execPath, ['--max-old-space-size=256', '-e', `
    const parser = require(${JSON.stringify(selectorPath)});
    const selector = '.a'.repeat(200000);
    const ast = parser().astSync(selector);
    if (ast.nodes[0].nodes.length !== 200000) process.exit(1);
  `], { timeout: 5000, encoding: 'utf8' });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});

test('Tailwind selector parsing preserves normal CSS', () => {
  const parser = tailwindRequire('postcss-selector-parser');
  const selector = 'a:hover > .card[data-state="open"], #main::before';
  assert.equal(parser().processSync(selector), selector);
});

test('PostCSS rejects hostile indexed source-map offsets', () => {
  const { SourceMapConsumer } = postcssRequire('source-map-js');
  const map = { version: 3, sources: ['input.js'], names: [], mappings: 'AAAA' };
  for (const line of [10000001, Infinity, -1, 0.5, '1']) {
    assert.throws(() => new SourceMapConsumer({
      version: 3, sections: [{ offset: { line, column: 0 }, map }],
    }), /Section offset/);
  }
  assert.throws(() => new SourceMapConsumer({
    version: 3,
    sections: [{ offset: { line: 6000000, column: 0 }, map: {
      version: 3, sections: [{ offset: { line: 6000000, column: 0 }, map }],
    } }],
  }), /Section offset/);
});

test('PostCSS source maps preserve normal mappings', () => {
  const { SourceMapConsumer, SourceMapGenerator } = require(sourceMapPath);
  const generator = new SourceMapGenerator({ file: 'output.js' });
  generator.addMapping({
    generated: { line: 1, column: 0 }, original: { line: 2, column: 3 }, source: 'input.js',
  });
  const consumer = new SourceMapConsumer(generator.toJSON());
  assert.deepEqual(consumer.originalPositionFor({ line: 1, column: 0 }), {
    source: 'input.js', line: 2, column: 3, name: null,
  });
});
