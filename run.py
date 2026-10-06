"""Start the server.

    Terminal / Anaconda Prompt:  python run.py
    Spyder:                       open this file and press F5 (Run)

Then open http://127.0.0.1:8000 (web app) or http://127.0.0.1:8000/docs (Swagger API).
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

    print(f"Bóveda IA en http://{HOST}:{PORT}  |  API: http://{HOST}:{PORT}/docs")
    if inside_running_loop:
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        print("Servidor ejecutándose en segundo plano. Para detenerlo reinicia el kernel de Spyder.")
    else:
        server.run()


if __name__ == "__main__":
    main()
