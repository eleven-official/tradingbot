# Loki Trading Dashboard

This repository now includes a Vercel-ready Next.js dashboard for the Loki trading platform.

## Local development

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Vercel deployment

1. Import this repository into Vercel.
2. Keep the default settings.
3. Set environment variables if your backend API needs them:

```bash
NEXT_PUBLIC_API_URL=https://your-backend.example.com
```

4. Deploy. Vercel will automatically run `npm install` and `npm run build`.

## Notes

- The dashboard is designed as a polished front-end layer for the Python trading bot.
- The Python trading engine remains separate and can be connected via API.
- The app is intentionally lightweight and self-contained so it works well on Vercel.
