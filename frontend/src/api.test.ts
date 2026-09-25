import { afterEach, describe, expect, it } from 'vitest'

import { clearAccessToken, hasAccessToken } from './api'
import { createRequestId } from './requestId'


class MemorySessionStorage {
  private values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
  clear() { this.values.clear() }
}

const storage = new MemorySessionStorage()
Object.defineProperty(globalThis, 'sessionStorage', { value: storage })

afterEach(() => storage.clear())

describe('access token storage', () => {
  it('reports an existing session token and clears it on sign-out', () => {
    storage.setItem('resolveflow_access_token', 'signed-token')

    expect(hasAccessToken()).toBe(true)
    clearAccessToken()
    expect(hasAccessToken()).toBe(false)
  })
})

describe('request tracing', () => {
  it('creates a safe request identifier for API propagation', () => {
    expect(createRequestId()).toMatch(/^[A-Za-z0-9._-]{8,100}$/)
  })
})
