// LLMInstructionRowKind selects how a row is gated at MCP initialize time.
//   per_server — injected only when at least one of its linked servers is in
//                the active token/client scope (default, current behaviour).
//   general    — always injected regardless of scope. server_ids are ignored.
export type LLMInstructionRowKind = 'per_server' | 'general'

export interface LLMInstructionRow {
  id?: string // undefined for new rows created in the builder
  kind: LLMInstructionRowKind
  title?: string
  body: string
  server_ids: string[]
  display_order?: number
}

export interface LLMInstruction {
  id: string
  title: string
  description?: string
  rows: LLMInstructionRow[]
  created_by?: string
  created_at: string
  updated_at: string
}

export interface LLMInstructionListResponse {
  llm_instructions: LLMInstruction[]
}

export interface CreateLLMInstructionRequest {
  title: string
  description?: string
  rows: LLMInstructionRow[]
}

export type UpdateLLMInstructionRequest = Partial<CreateLLMInstructionRequest>

export interface LLMInstructionUsage {
  token_ids: string[]
  oauth2_client_ids: string[]
}

// LLMInstructionRendered is the server-composed Markdown payload the admin UI
// shows as the "what the LLM will see" preview. Produced by the same Go
// composer that runs at MCP initialize time, so the preview stays in sync
// with the runtime output.
export interface LLMInstructionRendered {
  markdown: string
}
