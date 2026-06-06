vtarget = r"c:\VScode\Nexus\nexus\cli.py"

with open(target, "r", encoding="utf-8") as f:
    existing = f.read()

# Current state: file ends with "_setup_logging(args.verbose)\n"
# We need to append the rest of main() below it.
stub = "    _setup_logging(args.verbose)\n"
assert existing.endswith(stub), f"unexpected tail: {existing[-80:]!r}"

rest = """\
    ensure_dirs()

    # Apply --lang before running the command so that --help and any
    # i18n message are localised immediately.
    if getattr(args, "lang", None):
        set_language(args.lang)

    # Validate the config up-front so users see a clear error instead of
    # a confusing KeyError somewhere deep in the call stack.
    try:
        load_config(
            args.config if hasattr(args, "config") and args.config else None
        )
    except ConfigError as e:
        console.print(f"[red]{t('config.invalid', error=e)}[/red]")
        sys.exit(2)

    handler = COMMAND_MAP.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
"""

with open(target, "w", encoding="utf-8") as f:
    f.write(existing + rest)

import os
print("OK, file size:", os.path.getsize(target))
