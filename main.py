import sys
from app import build_app, parse_launch_options, setup_logging, configure_console
from CLI.commands import format_save
from Infra.storage import AppDataLocator
from version import __version__, APP_TITLE


def main(argv=None):
    configure_console()
    options = parse_launch_options(sys.argv[1:] if argv is None else argv)
    if options.show_version:
        print(f"{APP_TITLE} {__version__}")
        return 0

    data_dir = options.data_dir or AppDataLocator.resolve()
    setup_logging(data_dir, options.debug)
    ctx = build_app(data_dir, debug=options.debug)
    for message in ctx.messages:
        print(message)

    if options.rest:
        ctx.cli.exec_command(" ".join(options.rest))
        return 0

    print(f"{APP_TITLE} {__version__}" + (" [DEBUG]" if options.debug else ""))
    ctx.cli.exec_command("help")
    latest = ctx.saves.latest()
    if latest:
        print(f"\nЗнайдено збереження {format_save(latest)}. Щоб продовжити, введіть: continue")
    while True:
        try:
            cmd = input("\n> ").strip()
            if cmd in ("exit", "quit"):
                ctx.game_strategy.autosave()
                break
            if cmd:
                ctx.cli.exec_command(cmd)
        except (KeyboardInterrupt, EOFError):
            ctx.game_strategy.autosave()
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
