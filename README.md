## RabbitMQ Desktop Notifier (Python/Tkinter)

A lightweight desktop client that pairs with a backend via REST, then listens on RabbitMQ for user-targeted notifications. When a message arrives, it shows a fullscreen, always-on-top modal with optional reply and sends delivery/read/reply statuses back to the server.

### Features
- Pairing with server to obtain a unique routing token
- Consumption from RabbitMQ (direct exchange) using `pika`
- Fullscreen Tkinter UI with gradient, logo, message, optional reply
- Sends statuses back (`delivered`, `read`, `replied`) via RabbitMQ
- Heartbeat and sign-out REST endpoints to track client presence

### Project Layout
- `app/app_v2.py`: main, actively maintained client (Tkinter)
- `app/app.py`: earlier prototype (kept for reference)
- `app/app_pySide.py`: PySide6 prototype (kept for reference)

### Requirements
- Python 3.10+
- RabbitMQ reachable from the client
- Backend API exposing these endpoints:
  - `POST /pair/` accepts `external_ip`, `hostname` and returns `{ "token": "..." }`
  - `POST /terminal_heartbeat/` with `hostname`
  - `POST /terminal_sign_out/` with `hostname`

### Quick start
1) Create and activate a virtual environment.
2) Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3) Copy `.env.example` to `.env` and configure according to your environment.
4) Run the client:
   ```bash
   python app/app_v2.py
   ```

On first run, the app will attempt to pair with the server and store a token at `app/terminal_token.json`. On subsequent runs, it reuses this token.

### Environment variables
Create a `.env` file (see `.env.example`):
- `API_BASE_URL`: base URL of your backend (e.g., `http://localhost:8000`)
- `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USERNAME`, `RABBITMQ_PASSWORD`
- `TOKEN_FILE_PATH`: path to the local token file (default `app/terminal_token.json`)
- `HEARTBEAT_MINS`: heartbeat interval in minutes (default 3)

### Notes
- The UI optionally displays `Logo.png` from the repository root. If it's missing, the app will run without it.
- `app/app.py` and `app/app_pySide.py` are non-maintained prototypes; use `app/app_v2.py`.

### Docker
This project uses a GUI (Tkinter). Containers do not have a display by default, so running the GUI inside Docker is not supported out-of-the-box. The provided `Dockerfile` is aligned with the codebase but intended for future headless service mode or for building dependency images only.

### CI
Basic linting via flake8 is configured through GitHub Actions. You can run it locally via:
```bash
pip install flake8
flake8
```

### License
MIT — see `LICENSE`.

