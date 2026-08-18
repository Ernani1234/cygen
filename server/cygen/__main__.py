"""
Ponto de entrada do backend.

    python -m cygen              # sobe em http://127.0.0.1:8756
    python -m cygen --port 9000  # porta alternativa

O Electron sobe este processo como sidecar e espera a linha `CYGEN_READY` no
stdout antes de carregar a janela — assim a UI nunca aparece antes da API estar
de pé.
"""

from __future__ import annotations

import argparse
import socket
import sys


def free_port(preferred: int) -> int:
    """Devolve a porta desejada, ou outra livre se ela estiver ocupada."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(prog="cygen", description="Backend do Cygen")
    parser.add_argument("--port", type=int, default=8756)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true", help="recarrega ao salvar")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn não está instalado. Rode: pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    port = free_port(args.port)

    # O shell Electron lê esta linha para saber onde conectar.
    print(f"CYGEN_READY http://{args.host}:{port}", flush=True)

    uvicorn.run(
        "cygen.app:app" if args.reload else _load_app(),
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="warning",
        access_log=False,
    )
    return 0


def _load_app():
    from .app import app
    return app


if __name__ == "__main__":
    raise SystemExit(main())
