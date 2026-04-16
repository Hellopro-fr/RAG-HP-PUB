import { api } from './client'
import type {
  GoogleStatus,
  SheetInfo,
  SheetPreview,
  SheetImportRequest,
  SheetImportResponse
} from '@/types/google'

const BASE = '/api/v1'

export const googleApi = {
  getAuthUrl(): Promise<{ url: string }> {
    return api.get<{ url: string }>(`${BASE}/google/auth-url`)
  },

  getStatus(): Promise<GoogleStatus> {
    return api.get<GoogleStatus>(`${BASE}/google/status`)
  },

  disconnect(): Promise<void> {
    return api.del<void>(`${BASE}/google/disconnect`)
  },

  getSheetInfo(spreadsheetUrl: string): Promise<SheetInfo> {
    return api.post<SheetInfo>(`${BASE}/google/sheets/info`, { spreadsheet_url: spreadsheetUrl })
  },

  getSheetPreview(spreadsheetId: string, sheetName: string): Promise<SheetPreview> {
    return api.post<SheetPreview>(`${BASE}/google/sheets/preview`, {
      spreadsheet_id: spreadsheetId,
      sheet_name: sheetName
    })
  },

  importFromSheet(request: SheetImportRequest): Promise<SheetImportResponse> {
    return api.post<SheetImportResponse>(`${BASE}/google/sheets/import`, request)
  }
}
