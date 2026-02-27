import nubrastats as ns


def main() -> None:
    print("nubrastats version:", ns.__version__)
    print(
        "modules:",
        [m for m in ("stats", "plots", "reports", "adapters", "utils") if hasattr(ns, m)],
    )


if __name__ == "__main__":
    main()
