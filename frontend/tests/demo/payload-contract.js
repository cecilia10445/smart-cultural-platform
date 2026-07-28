import crypto from 'node:crypto'

// The preflight capture and the live recording must hash the same normalized
// JavaScript object, never the incidental bytes of a JSON file.
export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export function payloadSha256(value) {
  return crypto.createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex')
}
