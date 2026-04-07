import os

import uvicorn

from warehouse_env.server.app import app


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server.app:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
