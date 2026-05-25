"""Composition root for the FastAPI application.

Three thin layers replace the old 400-line `create_app`:

- `infrastructure` builds adapters (engine, repos, frame store, llm, decoder/listener).
- `application` builds services and use cases on top of the adapters.
- `interfaces` mounts middleware/lifespan/routers and returns the FastAPI app.

Each call site reaches dependencies via `request.app.state.container.X`; the
`container` is the sole attribute the composition writes to `app.state`.
"""
