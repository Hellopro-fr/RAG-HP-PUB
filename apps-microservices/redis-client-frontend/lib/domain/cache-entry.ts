// Domain: metadata for one Redis key shown in the browser.
// No `value` — the key browser never displays values (a value inspector is deferred).
export interface KeyMeta {
  key: string
  type: string // Redis TYPE: string | hash | set | zset | list | stream | none | unknown
  ttl?: number // seconds; undefined = no expiry
  size: number // bytes (MEMORY USAGE); 0 if unavailable
}
