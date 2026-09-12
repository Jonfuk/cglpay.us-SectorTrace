import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StLink from './StLink.vue'

// StLink is the ONLY component allowed to turn a source-derived URL into a
// hyperlink, so its validation is security-relevant: only http(s) may become an
// <a href>, everything else must render as inert text.
describe('StLink', () => {
  it('renders http and https as links', () => {
    for (const href of ['https://example.org/x', 'http://example.org']) {
      const w = mount(StLink, { props: { href } })
      expect(w.find('a').exists()).toBe(true)
      expect(w.find('a').attributes('href')).toBe(new URL(href).href)
    }
  })

  it('adds rel=noopener noreferrer for external links', () => {
    const w = mount(StLink, { props: { href: 'https://example.org' } })
    expect(w.find('a').attributes('rel')).toBe('noopener noreferrer')
  })

  it('refuses javascript:, data:, and other schemes — renders inert text, no <a>', () => {
    for (const href of [
      'javascript:alert(1)',
      'data:text/html,<script>1</script>',
      'vbscript:msgbox',
      'file:///etc/passwd',
    ]) {
      const w = mount(StLink, { props: { href } })
      expect(w.find('a').exists()).toBe(false)
    }
  })

  it('refuses a relative path (not a validated absolute http(s) URL)', () => {
    const w = mount(StLink, { props: { href: '/api/admin/secret' } })
    expect(w.find('a').exists()).toBe(false)
  })

  it('renders an em dash for null/empty', () => {
    const w = mount(StLink, { props: { href: null } })
    expect(w.find('a').exists()).toBe(false)
    expect(w.text()).toBe('—')
  })
})
