"""Start the server.

    Terminal / Anaconda Prompt:  python run.py
    Spyder:                       open this file and press F5 (Run)

Then open http://127.0.0.1:8000/docs (Swagger). The web interface runs separately: cd ../frontend && npm run dev
"""
import asyncio
import threading

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    server_config = uvicorn.Config("app.main:app", host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(server_config)

    try:
        asyncio.get_running_loop()
        inside_running_loop = True   # Spyder / Jupyter already have an event loop
    except RuntimeError:
        inside_running_loop = False

    print(f"API de Bóveda IA en http://{HOST}:{PORT}  |  Documentación: http://{HOST}:{PORT}/docs  |  Interfaz: http://localhost:5173 (npm run dev en frontend/)")
    if inside_running_loop:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        print("Servidor ejecutándose en segundo plano. Para detenerlo reinicia el kernel de Spyder.")
    else:
        server.run()


if __name__ == "__main__":
    main()
