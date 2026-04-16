# Analytics Copilot UI

A production-grade Next.js frontend for the Analytics Copilot project.

## Setup

1. Install dependencies:
   ```bash
   cd "analytics-copilot-ui"
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open the app in your browser at:
   ```
   http://localhost:3000
   ```

## Backend

The app expects the backend API at `http://localhost:8000` by default.

- `/v1/ask` - GET question endpoint
- `/upload` - POST dataset upload endpoint
- `/sessions` - GET existing sessions

If your backend runs on a different URL, update `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Notes

- Uses Tailwind CSS for styling.
- Uses Zustand for session state and persistence.
- Uses Plotly for rendering chart data returned from the backend.
- Validate that the backend responses match the expected API contract in `services/api.ts` and `types/index.ts`.
