import os

from waitress import serve

from src.utthan.web import create_app


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("UTTHAN_HOST", "127.0.0.1")
    port = int(os.environ.get("UTTHAN_PORT", "8080"))
    serve(app, host=host, port=port, threads=8)