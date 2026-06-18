from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AVR X-Ray - monitor interno do ATmega328P."
    )
    parser.add_argument("--port", help="Porta serial, por exemplo COM3 ou /dev/ttyACM0.")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate da Serial.")
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Usa dados simulados e nao requer Arduino.",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="Exibe os snapshots no terminal em vez da interface grafica.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.terminal:
        from terminal_dashboard import run_terminal_dashboard

        run_terminal_dashboard(
            port=args.port,
            baud=args.baud,
            simulate=args.simulate,
        )
        return

    from gui_app import run_gui

    run_gui(
        initial_port=args.port,
        baud=args.baud,
        simulate=args.simulate,
    )


if __name__ == "__main__":
    main()
