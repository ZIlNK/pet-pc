# External Integrations

**Analysis Date:** 2026-04-13

## APIs & External Services

**HTTP API Server (Built-in):**
- aiohttp-based REST API server
- Location: `src/desktop_pet/api_server.py`
- Default port: 8080
- Host: configurable (default 0.0.0.0)
- IP Whitelist: configurable (default localhost only: ["127.0.0.1", "::1"])
- CORS: enabled with wildcard origin (`Access-Control-Allow-Origin: *`)

**API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get pet position, state, mode, available animations |
| `/api/mode` | POST | Set mode: `{"mode": "random"}` or `{"mode": "motion"}` |
| `/api/move` | POST | Move to coordinates: `{"x": 100, "y": 200}` |
| `/api/move_by` | POST | Relative move: `{"dx": 50, "dy": 0}` |
| `/api/move_edge` | POST | Move to edge: `{"edge": "left"}` or `{"edge": "right"}` |
| `/api/animation` | POST | Play animation with optional callback URL |
| `/api/walk` | POST | Walk animation: `{"direction": "left"}` |
| `/api/animations` | GET | List available animations |

**Outbound Webhook Calls:**
- Animation completion callbacks via HTTP POST
- Callback URL validation (blocks private/internal IPs)
- Timeout: 5 seconds
- Payload: JSON with event, animation name, position, timestamp

## Data Storage

**Configuration Files:**
- Type: JSON files
- Location: `config/`
- Files:
  - `default_config.json` - Default configuration (committed)
  - `user_config.json` - User overrides (gitignored)
- Merging: Deep merge via ConfigManager

**Pet Packages:**
- Location: `pets/{pet_name}/`
- Structure:
  - `meta.json` - Pet metadata (name, author, version, images)
  - `animations/` - Animation files (GIF, WebP, PNG, APNG)
  - `config/actions.json` - Pet-specific actions (optional)

**File Storage:**
- Local filesystem only (no cloud storage)
- Animation assets stored in pet package directories
- User-configurable pet images

**Caching:**
- None (no caching layer)

## Authentication & Identity

**API Authentication:**
- IP whitelist-based access control
- Default: localhost only
- Configurable via `config/default_config.json` -> `api.allowed_ips`
- IP filtering can be disabled (for ngrok/tunneling)

**No external auth providers** - Application is self-contained

## Monitoring & Observability

**Logging:**
- Standard Python logging module
- Configurable log level (DEBUG, INFO, WARNING, ERROR)
- Log output: stdout via basicConfig
- Third-party library noise reduction (PIL, aiohttp set to WARNING)

**Error Tracking:**
- No external error tracking service
- Internal logging via Python `logging` module

## CI/CD & Deployment

**Build System:**
- hatchling (PEP 517 build backend)
- Produces wheel and source distribution

**Executable Build:**
- PyInstaller (dev dependency)
- Produces Windows .exe

**Version Control:**
- Git-based workflow
- No automated CI/CD pipeline detected

## Environment Configuration

**Configuration via JSON:**
- No environment variables required for core functionality
- API host/port configured in `config/default_config.json`

**Configuration Schema (api section):**
```json
{
  "api": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "allowed_ips": ["127.0.0.1", "::1"]
  }
}
```

## Platform Integration

**Windows Registry:**
- Startup registration via `winreg` module
- Registry key: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- Managed by: `src/desktop_pet/startup_manager.py`

**System Tray:**
- PyQt6 QSystemTrayIcon
- Minimize to tray support
- Tray menu for show/hide/quit

## Webhooks & Callbacks

**Incoming:**
- HTTP POST endpoints (API server above)
- JSON request body parsing
- IP whitelist filtering

**Outgoing:**
- Animation completion callbacks
- User-provided callback URLs
- Security: URL validation blocks internal/private IPs
- Timeout: 5 seconds
- Uses aiohttp ClientSession for async POST

---

*Integration audit: 2026-04-13*