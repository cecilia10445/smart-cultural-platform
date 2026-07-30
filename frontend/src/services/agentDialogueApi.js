import axios from 'axios'
import { createClientId } from '../utils/clientId'

const EMPTY = { brief_summary: null, product_design: null, visual_direction: null, final_result: null, messages: [], steps: [], error: null }

function asArray(value) { return Array.isArray(value) ? value : [] }
function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : null }

export function normalizeAgentSession(payload) {
  const raw = asObject(payload?.data ?? payload)
  if (!raw || typeof raw.session_id !== 'string' || typeof raw.status !== 'string') {
    const error = new Error('AGENT_DTO_INCOMPLETE')
    error.code = 'AGENT_DTO_INCOMPLETE'
    throw error
  }
  return {
    ...EMPTY, ...raw,
    revision_count: Number.isFinite(Number(raw.revision_count)) ? Number(raw.revision_count) : 0,
    brief_summary: asObject(raw.brief_summary), product_design: asObject(raw.product_design),
    visual_direction: asObject(raw.visual_direction), final_result: asObject(raw.final_result), error: asObject(raw.error),
    messages: asArray(raw.messages), steps: asArray(raw.steps),
  }
}

function headers() {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(method, url, data) {
  try {
    const response = await axios({ method, url, data, headers: headers() })
    if (response.data?.status !== 'success') {
      const error = new Error(response.data?.message || 'Agent request failed')
      error.code = response.data?.code || 'AGENT_API_ERROR'
      error.kind = 'business'
      throw error
    }
    return normalizeAgentSession(response.data)
  } catch (error) {
    if (error.code === 'AGENT_DTO_INCOMPLETE') error.kind = 'data'
    else if (!error.kind) error.kind = error.response ? 'business' : 'network'
    throw error
  }
}

export const createSession = () => request('post', '/api/v2/agent-design/sessions', {})
export const getSession = (sessionId) => request('get', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}`)
export const sendMessage = (sessionId, text, expectedStatus, expectedVersion) => request('post', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}/messages`, {
  client_turn_id: createClientId(), text, ...(expectedStatus ? { expected_status: expectedStatus } : {}), ...(expectedVersion ? { expected_version: expectedVersion } : {}),
})
export const submitDecision = (sessionId, decision, expectedStatus, expectedVersion) => request('post', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}/decisions`, {
  decision_id: createClientId(), decision, expected_status: expectedStatus, ...(expectedVersion ? { expected_version: expectedVersion } : {}),
})
