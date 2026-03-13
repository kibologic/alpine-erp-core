#!/usr/bin/env node
/**
 * Start Swite dev server for Alpine ERP
 */
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SwiteServer } from '@swissjs/swite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PYTHON_HOST = 'localhost';
const PYTHON_PORT = 8000;
const INTERNAL_TOKEN = process.env.INTERNAL_SERVICE_TOKEN || 'alpine_dev_internal_token_2026';

const server = new SwiteServer({
  root: path.resolve(__dirname, 'app'),
  publicDir: 'public',
  port: parseInt(process.env.PORT || '3000', 10),
  host: 'localhost',
  open: false,
  // rootDir expands Swite's serve root to the full monorepo so
  // imports from packages/ and modules/ resolve correctly (S-08)
  rootDir: path.resolve(__dirname, '..'),
});

// ── /api/v1/* proxy → FastAPI on port 8000 ───────────────────────────────────
// SwiteServer uses Express (server.app) but doesn't expose the underlying
// http.Server. Register the proxy directly on server.app BEFORE start() so
// it sits ahead of Swite's SPA catch-all fallback in the middleware chain.
// When Express mounts on '/api/v1', req.url inside the handler is the
// suffix after the mount point — prepend the prefix to reconstruct the path.

server.app.use('/api/v1', (req, res) => {
  const options = {
    hostname: PYTHON_HOST,
    port: PYTHON_PORT,
    path: `/api/v1${req.url}`,
    method: req.method,
    headers: {
      ...req.headers,
      host: `${PYTHON_HOST}:${PYTHON_PORT}`,
      'x-internal-token': INTERNAL_TOKEN,
    },
  };

  const proxy = http.request(options, (pythonRes) => {
    res.writeHead(pythonRes.statusCode, pythonRes.headers);
    pythonRes.pipe(res, { end: true });
  });

  proxy.on('error', (err) => {
    console.error('[proxy] FastAPI unreachable:', err.message);
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: 'FastAPI service unavailable' }));
  });

  req.pipe(proxy, { end: true });
});

console.log(`[proxy] /api/v1/* → http://${PYTHON_HOST}:${PYTHON_PORT}`);

await server.start();
