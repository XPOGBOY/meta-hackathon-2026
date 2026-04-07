import sys


def run_inference() -> None:
    from warehouse_env.inference import run_inference as package_run_inference

    package_run_inference()


if __name__ == "__main__":
    try:
        run_inference()
    except Exception as exc:
        print(f"[FATAL] root inference wrapper crashed: {exc}", file=sys.stderr)
