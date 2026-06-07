import sys
sys.path.insert(0, ".")

try:
    from nexus.commands.run import run_command, _render_response
    print("import OK")
except Exception as e:
    print("IMPORT ERROR:", type(e).__name__, e)
    raise
