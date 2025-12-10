import importlib
import traceback


def run_tests():
    mod_name = "test_azure_conn"
    mod = importlib.import_module(mod_name)
    failures = 0
    for name in dir(mod):
        if name.startswith("test_"):
            obj = getattr(mod, name)
            if callable(obj):
                try:
                    print(f"RUNNING {name}...", end=" ")
                    obj()
                    print("OK")
                except Exception:
                    failures += 1
                    print("FAIL")
                    traceback.print_exc()

    if failures:
        print(f"\n{failures} test(s) failed")
        raise SystemExit(1)
    else:
        print("\nAll tests passed")


if __name__ == "__main__":
    run_tests()
