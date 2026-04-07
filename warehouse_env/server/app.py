import os

from openenv.core.env_server import create_fastapi_app
from warehouse_env.server.environment import WarehouseEnvironment
from warehouse_env.models import WarehouseAction, WarehouseObservation

from fastapi.middleware.cors import CORSMiddleware

app = create_fastapi_app(
    WarehouseEnvironment,
    action_cls=WarehouseAction,
    observation_cls=WarehouseObservation
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/render")
async def render_env():
    # Note: This is simplified. In multi-session, we'd need to identify which session to render.
    # For local testing, we'll implement a simple one.
    from openenv.core.env_server.http_server import HTTPEnvServer
    # We can try to access the server's environment if it's singleton
    return {"render": "Render system active. Use logs to see the grid."}

@app.get("/")
async def root():
    return {"status": "ok", "message": "OpenEnv Warehouse Logistics API running."}

def main():
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("warehouse_env.server.app:app", host="0.0.0.0", port=port, reload=True)

if __name__ == "__main__":
    main()
