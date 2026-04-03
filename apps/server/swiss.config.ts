// S-01, S-02, S-03 in swite DIRECTIVE must be complete before this activates
// Workaround: run Python manually — uvicorn services.main:app --reload --port 8000

export default {
  server: {
    port: 3000,
  },
  services: {
    python: {
      entry: '../../services/main.py',
      port: 8000,
      autoStart: true,
      healthCheck: '/health',
    },
  },
}
