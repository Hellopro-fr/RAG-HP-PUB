export type Protocol = 'rest' | 'ws' | 'grpc'
export type Source = 'env' | 'manual' | 'scan'
export type Status = 'active' | 'deprecated' | 'down'

export interface ApiCatalogService {
  id: string
  name: string
  baseUrl: string
  protocols: Protocol[]
  source: Source
  status: Status
  description?: string
  owner?: string
  tags?: string[]
  apiInfoUrl?: string
  grpcAddress?: string
  lastScannedAt?: string
  lastScanOk?: boolean
  lastScanError?: string
  createdAt: string
  updatedAt: string
}

export interface ApiCatalogEndpoint {
  id: string
  serviceId: string
  protocol: Protocol
  method?: string
  path: string
  summary?: string
  operationId?: string
  tags?: string[]
  deprecated: boolean
}

export interface ListResp {
  items: ApiCatalogService[]
  total: number
}

export interface DetailResp {
  service: ApiCatalogService
  endpoints: ApiCatalogEndpoint[]
}

export interface CreateApiRequest {
  name: string
  baseUrl: string
  protocols: Protocol[]
  description?: string
  owner?: string
  tags?: string[]
  apiInfoUrl?: string
  grpcAddress?: string
}

export interface UpdateApiRequest {
  description?: string
  owner?: string
  tags?: string[]
  status?: Status
}

export interface RescanReport {
  servicesScanned: number
  servicesOk: number
  servicesFailed: number
  errors: string[]
  finishedAt?: string
}
