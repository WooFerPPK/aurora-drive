// Re-exports for the generated REST and WS type artifacts.
// The two `./api` and `./ws` files are produced by `make codegen`
// from the backend's OpenAPI dump and WebSocket JSON Schema dump.
// Do not import this file from the backend — it's TypeScript only.

export * from "./api.js";
export * from "./ws.js";
