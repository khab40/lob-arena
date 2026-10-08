import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { URL } from 'node:url'

const frontend = JSON.parse(readFileSync(new URL('../package.json', import.meta.url)))
const website = JSON.parse(readFileSync(new URL('../../website/package.json', import.meta.url)))

test('shared frontend and website lockfile uses matching dependency specifiers', () => {
  assert.deepEqual(website.dependencies, frontend.dependencies)
  assert.deepEqual(website.devDependencies, frontend.devDependencies)
  assert.deepEqual(website.pnpm, frontend.pnpm)
})
