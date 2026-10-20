// pm2 definition for Dojo Manager. Normally started through ./start.sh, which builds the
// frontend, applies migrations and passes DOJO_HOST / DOJO_PORT from backend/.env.
//
//   pm2 status | pm2 logs dojo | pm2 restart dojo
const path = require("path");

const backend = path.join(__dirname, "backend");

module.exports = {
  apps: [
    {
      name: "dojo",
      cwd: backend,
      // One process serves the API and the built web app (frontend/dist).
      script: path.join(backend, ".venv", "bin", "uvicorn"),
      interpreter: "none",
      args: [
        "app.main:app",
        "--host", process.env.DOJO_HOST || "0.0.0.0",
        "--port", process.env.DOJO_PORT || "8090",
        "--no-server-header",
        "--timeout-graceful-shutdown", "10",
      ],
      env: { PYTHONUNBUFFERED: "1" },
      autorestart: true,
      min_uptime: "10s",
      max_restarts: 10,
      restart_delay: 3000,
      kill_timeout: 12000,
      time: true,
    },
  ],
};
