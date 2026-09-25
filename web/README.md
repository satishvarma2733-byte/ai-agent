# aVn Agent UI

Production-ready operations console for the **aVn Agent** backend (Gemini Live branch).

Built with **Vite + React + TypeScript + Tailwind CSS v4**.

---

## Quick Start

### 1. Install dependencies

```bash
cd web
npm install
```

### 2. Configure the backend URL

```bash
cp .env.example .env
```

Edit `.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Replace `http://localhost:8000` with the actual URL where your aVn Agent backend is running.

### 3. Start the dev server

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start dev server on `0.0.0.0:5173` |
| `npm run build` | Build production bundle to `dist/` |
| `npm run preview` | Serve production build on `0.0.0.0:5173` |

---

## How it connects to the backend

The frontend is **completely separate** from the backend. It communicates exclusively via HTTP/REST.

All requests go to `VITE_API_BASE_URL` (default: `http://localhost:8000`). The frontend reads this at build time via Vite's env injection.

**CORS**: The backend must allow requests from the origin where the frontend is deployed. For local dev, if both run on `localhost`, there's no issue.

### API surface used

| Page | Endpoints |
|---|---|
| Overview | `GET /health`, `GET /api/stats`, `GET /api/logs`, `GET /api/appointments`, `GET /api/kb/status` |
| Configuration | `GET /api/config`, `POST /api/config` |
| Call Logs | `GET /api/logs`, `GET /api/logs/{id}/transcript` |
| Contacts | `GET /api/contacts` |
| Appointments | `GET /api/appointments`, `POST /api/appointments`, `PATCH /api/appointments/{id}`, `POST /api/appointments/{id}/cancel` |
| Knowledge Base | `GET /api/kb/status`, `GET /api/kb/sources`, `POST /api/kb/sources`, `PATCH /api/kb/sources/{id}`, `DELETE /api/kb/sources/{id}`, `POST /api/kb/sources/{id}/sync`, `POST /api/kb/upload`, `GET /api/kb/jobs`, `POST /api/kb/search` |
| Outbound Calls | `POST /api/call/single`, `POST /api/call/bulk` |

---

## Deployment

The `dist/` folder is a static SPA. Deploy it to any static host (Nginx, Vercel, Netlify, S3+CloudFront).

**Important**: Set `VITE_API_BASE_URL` to point at your live backend before running `npm run build`.

---

## Project structure

```
src/
  api/          API client layer (typed, modular)
  components/
    layout/     Sidebar + page header
    ui/         Button, Badge, Modal, Table, Input, Toggle, etc.
  pages/        One file per route
  types/        Shared TypeScript interfaces (derived from backend contract)
  index.css     Design system tokens + Tailwind v4 theme
  App.tsx       Router
  main.tsx      Entry
```
