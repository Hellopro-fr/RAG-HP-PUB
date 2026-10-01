import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ProtocolBadge from './ProtocolBadge.vue'

describe('ProtocolBadge', () => {
  it('renders REST label with blue style', () => {
    const w = mount(ProtocolBadge, { props: { protocol: 'rest' } })
    expect(w.text()).toBe('REST')
    expect(w.classes()).toContain('bg-blue-100')
  })

  it('renders WS label with purple style', () => {
    const w = mount(ProtocolBadge, { props: { protocol: 'ws' } })
    expect(w.text()).toBe('WS')
    expect(w.classes()).toContain('bg-purple-100')
  })

  it('renders gRPC label with green style', () => {
    const w = mount(ProtocolBadge, { props: { protocol: 'grpc' } })
    expect(w.text()).toBe('gRPC')
    expect(w.classes()).toContain('bg-green-100')
  })
})
