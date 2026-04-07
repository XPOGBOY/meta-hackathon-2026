from warehouse_env.inference import run_inference


if __name__ == "__main__":
    try:
        run_inference()
    except Exception as exc:
        print(f"[FATAL] root inference wrapper crashed: {exc}")
