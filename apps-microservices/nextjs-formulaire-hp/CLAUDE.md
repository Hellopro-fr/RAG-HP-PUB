# nextjs-formulaire-hp

Multi-step product questionnaire form for buyer-supplier matching.

## Tech Stack

- **Framework:** Next.js 14 (React 18, TypeScript)
- **UI:** Radix UI, Tailwind CSS 3, shadcn/ui
- **State:** Zustand
- **Data Fetching:** TanStack React Query
- **Forms:** React Hook Form + Zod
- **Package Manager:** npm
- **Runtime:** Node.js >= 20

## Commands

| Action | Command |
|--------|---------|
| Dev | `npm run dev` |
| Build | `npm run build` |
| Start | `npm run start` |
| Lint | `npm run lint` (next lint) |

## Docker

- Multi-stage build (alpine), standalone output
- Port: **3000**
- Base path: `/formulaire`
- Served behind Apache reverse proxy

## Folder Structure

```
app/
  (flow)/              # Route group for multi-step wizard
    choice/            # Category choice step
    contact-simple/    # Contact form step
    geo-zone/          # Geographic zone selection
    profile/           # Buyer profile step
    questionnaire/     # Dynamic questionnaire
    selection/         # Supplier selection
    something-to-add/  # Additional info step
  api/                 # Next.js API routes
    buyer/             # Buyer verification
    caracteristiques/  # Product characteristics
    category-token/    # Encrypted category tokens
    demande-info/      # Info request
    geo/               # Geographic data
    images/            # Image proxy
    info-categorie/    # Category info
    matching/          # Supplier matching
    matching_fournisseur/
    pdt/, tck/, questionnaire/, siren/, siret/
  confirmation/        # Final confirmation page
components/
data/
types/
middleware.ts          # Auth/routing middleware
```

## API Endpoints (Next.js Routes)

- `GET /api/caracteristiques` -- Product characteristics
- `GET /api/geo` -- Geographic data
- `GET /api/info-categorie/[id]` -- Category info
- `POST /api/questionnaire/q1` -- First question
- `POST /api/questionnaire/qn` -- Follow-up questions
- `POST /api/matching` -- Supplier matching
- `POST /api/demande-info` -- Info request submission
- `GET /api/siren/search`, `GET /api/siret/search` -- Company lookups
- `POST /api/buyer/check` -- Buyer verification
- `GET /api/category-token` -- Token generation

## Conventions

- `basePath: '/formulaire'`, `output: 'standalone'`, security headers enabled.

## Dependencies

External APIs for supplier matching, category data, company lookups (INSEE).
