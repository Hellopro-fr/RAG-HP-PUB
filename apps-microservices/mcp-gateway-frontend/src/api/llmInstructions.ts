import { api } from './client'
import type {
  LLMInstruction,
  LLMInstructionListResponse,
  CreateLLMInstructionRequest,
  UpdateLLMInstructionRequest,
  LLMInstructionUsage,
  LLMInstructionRendered
} from '@/types/llmInstruction'

const BASE = '/api/v1/llm-instructions'

export const llmInstructionsApi = {
  list(serverIds?: string[]): Promise<LLMInstructionListResponse> {
    const params = serverIds && serverIds.length > 0 ? { server_ids: serverIds.join(',') } : undefined
    return api.get<LLMInstructionListResponse>(BASE, params)
  },

  get(id: string): Promise<LLMInstruction> {
    return api.get<LLMInstruction>(`${BASE}/${id}`)
  },

  create(data: CreateLLMInstructionRequest): Promise<LLMInstruction> {
    return api.post<LLMInstruction>(BASE, data)
  },

  update(id: string, data: UpdateLLMInstructionRequest): Promise<LLMInstruction> {
    return api.put<LLMInstruction>(`${BASE}/${id}`, data)
  },

  remove(id: string): Promise<void> {
    return api.del<void>(`${BASE}/${id}`)
  },

  getUsage(id: string): Promise<LLMInstructionUsage> {
    return api.get<LLMInstructionUsage>(`${BASE}/${id}/usage`)
  },

  getRendered(id: string): Promise<LLMInstructionRendered> {
    return api.get<LLMInstructionRendered>(`${BASE}/${id}/rendered`)
  }
}
