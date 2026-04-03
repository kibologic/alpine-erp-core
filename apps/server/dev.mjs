#!/usr/bin/env node
/**
 * Start Swite dev server for Alpine ERP
 */
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SwiteServer } from '@kibologic/swite';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PYTHON_HOST = '127.0.0.1';
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

server.app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', 'http://localhost:3100');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }
  next();
});

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

// ── @kibologic/shell static CSS files ────────────────────────────────────────────
// Swite doesn't serve CSS from node_modules — serve them explicitly
const SHELL_ROOT = path.resolve(__dirname, 'node_modules/@kibologic/shell');
server.app.use('/node_modules/@kibologic/shell', (req, res, next) => {
  if (!req.url.endsWith('.css')) return next();
  const filePath = path.join(SHELL_ROOT, req.url);
  try {
    const css = readFileSync(filePath, 'utf-8');
    res.setHeader('Content-Type', 'text/css');
    res.end(css);
  } catch {
    next();
  }
});

await server.start();
