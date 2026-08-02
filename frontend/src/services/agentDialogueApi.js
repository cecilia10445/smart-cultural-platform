import axios from 'axios'
import { createClientId } from '../utils/clientId'

const EMPTY = { brief_summary: null, product_design: null, visual_direction: null, final_result: null, messages: [], steps: [], error: null }

function asArray(value) { return Array.isArray(value) ? value : [] }
function asObject(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : null }

function normalizeList(payload) {
  const raw = payload?.data
  if (!Array.isArray(raw)) throw Object.assign(new Error('AGENT_DTO_INCOMPLETE'), { code: 'AGENT_DTO_INCOMPLETE' })
  return raw.filter((item) => item && typeof item.session_id === 'string').map((item) => ({
    session_id: item.session_id, title: typeof item.title === 'string' ? item.title : '新建文创对话',
    status: typeof item.status === 'string' ? item.status : 'created', updated_at: item.updated_at || '',
    has_pending_action: item.has_pending_action === true,
  }))
}

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

async function rawRequest(method, url, data) {
  try {
    const response = await axios({ method, url, data, headers: headers() })
    if (response.data?.status !== 'success') throw Object.assign(new Error(response.data?.message || 'Agent request failed'), { code: response.data?.code || 'AGENT_API_ERROR', kind: 'business' })
    return response.data
  } catch (error) {
    if (!error.kind) error.kind = error.response ? 'business' : 'network'
    throw error
  }
}

export const createSession = () => request('post', '/api/v2/agent-design/sessions', {})
export const listSessions = async () => normalizeList(await rawRequest('get', '/api/v2/agent-design/sessions'))
export const getSession = (sessionId) => request('get', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}`)
export const runAssistantTurn = (sessionId, content, clientTurnId, taskId = null) => rawRequest('post', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}/assistant-turns`, { content, client_turn_id: clientTurnId, ...(taskId ? { task_id: taskId } : {}) })
export const getAssistantTurn = (sessionId, runId) => rawRequest('get', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}/assistant-turns/${encodeURIComponent(runId)}`)
export const sendMessage = (sessionId, text, expectedStatus, expectedVersion) => request('post', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}/messages`, {
  client_turn_id: createClientId(), text, ...(expectedStatus ? { expected_status: expectedStatus } : {}), ...(expectedVersion ? { expected_version: expectedVersion } : {}),
})
export const submitDecision = (sessionId, decision, expectedStatus, expectedVersion) => request('post', `/api/v2/agent-design/sessions/${encodeURIComponent(sessionId)}/decisions`, {
  decision_id: createClientId(), decision, expected_status: expectedStatus, ...(expectedVersion ? { expected_version: expectedVersion } : {}),
})

const segment = (value) => encodeURIComponent(value)
export const listTasks = (sessionId) => rawRequest('get', `/api/v2/agent-design/sessions/${segment(sessionId)}/tasks`).then((payload) => asArray(payload.data))
export const createTask = (sessionId, data) => rawRequest('post', `/api/v2/agent-design/sessions/${segment(sessionId)}/tasks`, data).then((payload) => payload.data)
export const selectTask = (sessionId, taskId, expectedSessionVersion) => rawRequest('post', `/api/v2/agent-design/sessions/${segment(sessionId)}/tasks/${segment(taskId)}/select`, { ...(expectedSessionVersion ? { expected_session_version: expectedSessionVersion } : {}) }).then((payload) => payload.data)
export const listArtifacts = (sessionId, taskId, options = {}) => {
  const query = new URLSearchParams()
  if (options.artifactType) query.set('artifact_type', options.artifactType)
  if (options.status) query.set('status', options.status)
  if (options.includeLegacy) query.set('include_legacy', 'true')
  const suffix = query.size ? `?${query.toString()}` : ''
  const base = taskId
    ? `/api/v2/agent-design/sessions/${segment(sessionId)}/tasks/${segment(taskId)}/artifacts`
    : `/api/v2/agent-design/sessions/${segment(sessionId)}/artifacts`
  return rawRequest('get', `${base}${suffix}`).then((payload) => asArray(payload.data))
}
export const listActions = (sessionId, taskId) => {
  const base = taskId
    ? `/api/v2/agent-design/sessions/${segment(sessionId)}/tasks/${segment(taskId)}/actions`
    : `/api/v2/agent-design/sessions/${segment(sessionId)}/actions`
  return rawRequest('get', base).then((payload) => asArray(payload.data))
}
export const getAvailableActions = (sessionId) => rawRequest('get', `/api/v2/agent-design/sessions/${segment(sessionId)}/available-actions`).then((payload) => asArray(payload.data))
export const getAgentGenerationHistory = (generationLogId) => rawRequest('get', `/api/v2/agent-design/history/generation-logs/${segment(generationLogId)}`).then((payload) => payload.data)
export const getRuntimeActionProposal = (sessionId, runId, actionType) => rawRequest('get', `/api/v2/agent-design/sessions/${segment(sessionId)}/assistant-turns/${segment(runId)}/action-proposal?action_type=${segment(actionType)}`).then((payload) => payload.data)
export const requestAction = (sessionId, taskId, data) => {
  const base = taskId
    ? `/api/v2/agent-design/sessions/${segment(sessionId)}/tasks/${segment(taskId)}/actions`
    : `/api/v2/agent-design/sessions/${segment(sessionId)}/actions`
  return rawRequest('post', base, data)
}
export const approveAction = (actionId, data) => rawRequest('post', `/api/v2/agent-design/actions/${segment(actionId)}/approve`, data)
export const rejectAction = (actionId, data) => rawRequest('post', `/api/v2/agent-design/actions/${segment(actionId)}/reject`, data)
export const executeAction = (actionId, data) => rawRequest('post', `/api/v2/agent-design/actions/${segment(actionId)}/execute`, data)
