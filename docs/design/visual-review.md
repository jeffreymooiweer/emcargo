# Reproducing the visual review

Use a local installation with synthetic data for ordinary browser testing. The
optional development bridge supports environments where the Vite preview process
and Python cannot share a network namespace. It forwards HTTP requests through a
file queue to a real FastAPI `TestClient`, with a fresh temporary database and a
synthetic administrator. It does not mock calculation, validation or export.

From the repository root, with backend and frontend dependencies installed:

```bash
python scripts/visual_review_worker.py --queue frontend/.review-bridge
```

In another terminal, enable the bridge for that development session only:

```bash
cd frontend
EMCARGO_VISUAL_REVIEW=true npm run dev
```

The worker creates three synthetic shipments. Add `--empty` for empty-state
review. `frontend/review.html` embeds the real application at 390px or 768px for
responsive CSS review; it is not a mobile-device emulator. Production builds have
only `index.html` as their entry and do not contain the review page or bridge.
The environment flag is read by Vite in development mode only. Production,
ordinary development and the native/Docker entrypoints never start the worker.
Do not enable this development fixture on a live installation.

Stop the worker and preview after the review. The temporary database is removed
when the worker exits. The ignored queue and local environment file must not be
committed. To return to normal API proxying, unset `EMCARGO_VISUAL_REVIEW` (and
remove it from any local environment file) and restart Vite.

Review the actual rendered images together with backend/UI tests. Screenshots
cannot establish export correctness, authorization, keyboard focus behavior or
physical mobile-device support on their own.
