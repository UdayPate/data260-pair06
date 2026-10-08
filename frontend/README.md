# Handshake Clone: React frontend (Pair 06)

React 18 + Vite + React Router + Axios + Bootstrap 5 (react-bootstrap).

| Setting | Value |
|---|---|
| Dev server | http://localhost:9061 (PORT_BASE 9060 + 1) |
| Backend API | http://localhost:9060 (change with `VITE_API_URL` in `.env`) |

```powershell
npm install
npm run dev      # start the app
npm test         # run the frontend tests (no backend needed)
npm run build    # production build into dist/
```

## Folder layout

| Folder | What lives there |
|---|---|
| `src/pages` | One file per screen (Login, Signup, Home, ...) |
| `src/components` | Reusable pieces (Navbar, Loading, ErrorAlert, ProtectedRoute, ...) |
| `src/services` | Every call to the backend. Pages never call Axios directly |
| `src/context` | Who is logged in (AuthContext) |
| `src/hooks` | Shared hooks (`useAsync`: loading / error / data) |
| `src/utils` | Small helpers (turning API errors into readable messages) |
| `src/test` | Tests |
