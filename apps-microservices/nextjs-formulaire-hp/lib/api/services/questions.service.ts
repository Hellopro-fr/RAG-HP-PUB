// ========================================
// QUESTIONS SERVICE - API CALLS
// ========================================

import { get } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';
import type { Question, ApiResponse } from '@/types';
import { QUESTIONS_DATA } from '@/data/questions';

/**
 * Fetch all questions from API
 * Falls back to local data if API is not available
 */
export async function fetchQuestions(): Promise<ApiResponse<Question[]>> {
  try {
    const response = await get<Question[]>(ENDPOINTS.questions.list());

    // If API fails, return local mock data
    if (response.error || !response.data) {
      return {
        data: QUESTIONS_DATA,
        error: null,
        status: 200,
      };
    }

    return response;
  } catch {
    // Fallback to local data
    return {
      data: QUESTIONS_DATA,
      error: null,
      status: 200,
    };
  }
}

/**
 * Fetch a single question by ID
 */
export async function fetchQuestionById(id: number): Promise<ApiResponse<Question>> {
  try {
    const response = await get<Question>(ENDPOINTS.questions.getById(id));

    // Fallback to local data
    if (response.error || !response.data) {
      const question = QUESTIONS_DATA.find(q => q.id === id);
      return {
        data: question || null,
        error: question ? null : 'Question not found',
        status: question ? 200 : 404,
      };
    }

    return response;
  } catch {
    const question = QUESTIONS_DATA.find(q => q.id === id);
    return {
      data: question || null,
      error: question ? null : 'Question not found',
      status: question ? 200 : 404,
    };
  }
}
