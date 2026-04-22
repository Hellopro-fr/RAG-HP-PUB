import type { PublicToolDetail } from './public'

export interface DocsConfigStep {
  type?: string
  title: string
  description: string
  link?: string
  image?: string
}

export interface DocsConfigGuide {
  authType: string
  steps: DocsConfigStep[]
}

export interface DocsServerSummary {
  slug: string
  name: string
  description: string
  icon?: string
  tools_count: number
}

export interface DocsServerDetail extends DocsServerSummary {
  tools: PublicToolDetail[]
  config_guide?: DocsConfigGuide
}
