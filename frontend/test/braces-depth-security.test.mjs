import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import process from 'node:process';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

// Resolve from the invoking app: the website imports this suite too.
const appRequire = createRequire(pathToFileURL(resolve('package.json')));
const tailwindRequire = createRequire(appRequire.resolve('tailwindcss'));
const chokidarRequire = createRequire(tailwindRequire.resolve('chokidar'));
const globRequire = createRequire(tailwindRequire.resolve('fast-glob'));
const micromatchPath = globRequire.resolve('micromatch');
const micromatchRequire = createRequire(micromatchPath);
const bracesPath = chokidarRequire.resolve('braces');
const braces = chokidarRequire('braces');
const nested = (depth, open = '(', close = ')') => open.repeat(depth) + 'x' + close.repeat(depth);
const depthError = error => /exceeds max depth/.test(error.message)
  && !/Maximum call stack/.test(error.message);

// A broken guard must fail promptly, even for a cyclic hand-built AST.
function boundedProbe(source) {
  const result = spawnSync(process.execPath, ['--stack_size=256', '-e', `
    const assert = require('node:assert/strict');
    const braces = require(${JSON.stringify(bracesPath)});
    const depthError = ${depthError.toString()};
    ${source}
  `], { encoding: 'utf8', timeout: 3000 });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
}

test('both Tailwind dependency paths load the patched braces instance', () => {
  assert.equal(micromatchRequire.resolve('braces'), bracesPath);
  assert.throws(() => globRequire('micromatch').braceExpand(nested(101, '{', '}')), depthError);
  assert.deepEqual(globRequire('micromatch').braceExpand('src/*.{ts,tsx}'), ['src/*.ts', 'src/*.tsx']);
});

test('all string APIs reject excessive brace, parenthesis and mixed nesting', () => {
  for (const method of ['parse', 'compile', 'expand', 'stringify']) {
    for (const pattern of [nested(101), nested(101, '{', '}'), nested(51, '{(', ')}'), '('.repeat(101)]) {
      assert.throws(() => braces[method](pattern), depthError, `${method}: ${pattern.slice(0, 8)}`);
    }
    assert.doesNotThrow(() => braces[method](nested(100)));
    assert.doesNotThrow(() => braces[method](nested(100, '{', '}')));
  }
});

test('the reported sub-10000-character input cannot exhaust a small stack', () => {
  boundedProbe(`
    const input = '('.repeat(4400) + 'x' + ')'.repeat(4400);
    for (const method of ['compile', 'expand', 'stringify']) {
      assert.throws(() => braces[method](input), depthError);
    }
  `);
});

test('direct AST APIs cannot bypass depth checks or loop on child cycles', () => {
  boundedProbe(`
    for (const method of ['compile', 'expand', 'stringify']) {
      let ast = { type: 'text', value: 'x' };
      for (let i = 0; i < 15000; i++) ast = { type: 'paren', nodes: [ast] };
      assert.throws(() => braces[method]({ type: 'root', nodes: [ast] }), depthError);
      const cycle = { type: 'paren', nodes: [] };
      cycle.nodes.push(cycle);
      assert.throws(() => braces[method]({ type: 'root', nodes: [cycle] }), depthError);
    }
  `);
});

test('expansion rejects cyclic parent chains before searching for a queue', () => {
  boundedProbe(`
    for (const pair of [false, true]) {
      const node = { type: 'paren', nodes: [{ type: 'text', value: 'x' }] };
      node.parent = pair ? { type: 'paren', parent: node } : node;
      assert.throws(() => braces.expand(node), /AST parent chain contains a cycle/);
    }
  `);
});

test('maxDepth can tighten but never disable the cap', () => {
  for (const method of ['parse', 'compile', 'expand', 'stringify']) {
    for (const maxDepth of [Infinity, NaN, '1000', 1000]) {
      assert.throws(() => braces[method](nested(101), { maxDepth }), depthError);
    }
    assert.doesNotThrow(() => braces[method](nested(1), { maxDepth: 1.5 }));
    assert.throws(() => braces[method](nested(2), { maxDepth: 1.5 }), depthError);
    assert.doesNotThrow(() => braces[method]('plain', { maxDepth: 0 }));
    assert.throws(() => braces[method]('(x)', { maxDepth: 0 }), depthError);
  }
  for (const method of ['compile', 'expand', 'stringify']) {
    const ast = () => braces.parse('((x))');
    assert.doesNotThrow(() => braces[method](ast(), { maxDepth: 2 }));
    assert.throws(() => braces[method](ast(), { maxDepth: 1.5 }), depthError);
  }
});

test('ordinary globs, ranges, literals and parser parent links retain their behavior', () => {
  assert.deepEqual(braces.expand('src/*.{ts,tsx}'), ['src/*.ts', 'src/*.tsx']);
  assert.deepEqual(braces.expand('item{1..3}'), ['item1', 'item2', 'item3']);
  assert.deepEqual(braces('src/*.{ts,tsx}'), ['src/*.(ts|tsx)']);
  const literalPatterns = ['\\('.repeat(101), '[' + '('.repeat(101) + ']', '"' + '{'.repeat(101) + '"'];
  for (const pattern of literalPatterns) assert.doesNotThrow(() => braces.expand(pattern));
  const ast = braces.parse('a{b,c}(d)');
  assert.equal(ast.nodes.find(node => node.type === 'brace').parent, ast);
  assert.equal(braces.stringify(ast), 'a{b,c}(d)');
  assert.equal(braces.stringify(braces.parse('{a}'), { escapeInvalid: true }), '{a}');
});
