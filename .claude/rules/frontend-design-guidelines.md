# Frontend Design Guidelines

> Apply when building UI components, pages, or web applications.

## Before Coding

1. **Purpose** — What problem does this interface solve? Who uses it?
2. **Tone** — Pick a deliberate aesthetic direction (minimal, editorial, brutalist, luxury, playful, etc.)
3. **Differentiation** — What makes this memorable? One thing someone will remember.

## Implementation Principles

- **Typography**: Distinctive, characterful fonts. Avoid generic (Inter, Roboto, Arial, system fonts).
- **Color**: Cohesive palette via CSS variables. Dominant color + sharp accents.
- **Motion**: CSS-only for HTML, Motion library for React. Focus on page load reveals, scroll-trigger, hover states.
- **Layout**: Unexpected compositions — asymmetry, overlap, grid-breaking. Avoid cookie-cutter patterns.
- **Detail**: Atmosphere via gradients, textures, layered transparencies, shadows.

## Anti-Patterns (Never)

- Generic AI aesthetics (Inter + purple gradient on white)
- Predictable layouts and component patterns
- Design without a clear point-of-view

## Philosophy

Bold maximalism and refined minimalism both work — the key is intentionality, not intensity.
Complexity of implementation must match the aesthetic vision.
