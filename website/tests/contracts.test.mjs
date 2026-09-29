import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { URL } from 'node:url';
import test from 'node:test';
import { nextFrame, replays } from '../src/data/replay.ts';
import { evidence, research, sourceCommit } from '../src/data/research.ts';

test('replay stops at the last frame, preserving evidence', () => {
  assert.equal(nextFrame(0, 10), 1);
  assert.equal(nextFrame(8, 10), 9);
  assert.equal(nextFrame(9, 10), 9);
  assert.equal(nextFrame(0, 1), 0);
});
test('bundled scenarios have consistent timelines and distinct evidence outcomes', () => {
  for (const replay of replays) {
    assert.equal(replay.frames.length, 10);
    replay.frames.forEach((frame, i) => {
      assert.equal(frame.second, i);
      assert.ok(frame.price > 0 && frame.bidSize > 0 && frame.askSize > 0);
      assert.ok(frame.event && frame.phase);
    });
  }
  assert.equal(replays[0].frames[6].flag, false);
  assert.equal(replays[0].frames[7].flag, true);
  assert.ok(replays[1].frames.every((frame) => !frame.flag));
});
test('qualification and immutable evidence boundaries stay explicit', () => {
  assert.equal(research.lightgbm, 'research_baseline_qualified');
  assert.equal(research.transformer, 'Readiness / input verification');
  assert.match(research.direction, /target, not a production capability/);
  for (const url of Object.values(evidence)) assert.ok(url.includes(`/blob/${sourceCommit}/docs/`));
});
test('the shared dependency lock is compatible with both app manifests', () => {
  const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
  const website = read('../package.json');
  const frontend = read('../../frontend/package.json');
  for (const key of ['dependencies', 'devDependencies', 'pnpm', 'packageManager']) {
    assert.deepEqual(website[key], frontend[key], `Update the shared-lock contract for ${key}`);
  }
});
