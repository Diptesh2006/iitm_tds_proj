# IIT Madras AI-Powered Python Code Interpreter

FastAPI service exposing `POST /code-interpreter` and `GET /health`. Submitted code runs in a separate isolated Python process with a strict timeout, isolated mode, a temporary working directory, and a minimal environment. The API process never executes submitted code.

## Local use

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # set AIPIPE_TOKEN if AI analysis is desired
uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
curl -X POST http://localhost:8000/code-interpreter -H "Content-Type: application/json" -d "{\"code\":\"print(15)\"}"
pytest -q
```

## Render deployment

1. Push this directory to a GitHub repository.
2. In Render, choose **New > Blueprint**, select the repository, and apply `render.yaml`.
3. Set the secret `AIPIPE_TOKEN` in the service environment variables.
4. After the first deploy, use `https://YOUR-RENDER-SERVICE.onrender.com/code-interpreter`.

Render web services do not provide a strong multi-tenant sandbox or hard resource limits for arbitrary Python. This project adds process isolation, `-I -S`, environment scrubbing, a temporary directory, and timeout, but production use with hostile users should move execution to a dedicated sandbox service/container with OS-level seccomp, cgroups, read-only filesystem, and network denial. Never expose this endpoint publicly without that additional isolation for untrusted users.
