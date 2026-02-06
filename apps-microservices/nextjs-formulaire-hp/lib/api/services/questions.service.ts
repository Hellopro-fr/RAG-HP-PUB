// ========================================
// QUESTIONS SERVICE - API CALLS
// ========================================

import { get } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';
import type { Question, ApiResponse } from '@/types';

/**
 * Fetch all questions from API
 */
export async function fetchQuestions(): Promise<ApiResponse<Question[]>> {
  const response = await get<Question[]>(ENDPOINTS.questions.list());
  return response;
}

/**
 * Fetch a single question by ID
 */
export async function fetchQuestionById(id: number): Promise<ApiResponse<Question>> {
  const response = await get<Question>(ENDPOINTS.questions.getById(id));
  return response;
}
