#!/usr/bin/env python3
"""Debug script to test imports before starting uvicorn."""
import sys
import traceback

print("=== Kenbot Dashboard API - Import Check ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"Path: {sys.path}", flush=True)

try:
    print("Importing fastapi...", flush=True)
    import fastapi
    print(f"  OK: {fastapi.__version__}", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)
    traceback.print_exc()

try:
    print("Importing supabase...", flush=True)
    from supabase import create_client
    print("  OK", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)
    traceback.print_exc()

try:
    print("Importing openai...", flush=True)
    import openai
    print(f"  OK: {openai.__version__}", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)
    traceback.print_exc()

try:
    print("Importing server module...", flush=True)
    import server
    print("  OK - server.app loaded", flush=True)
except Exception as e:
    print(f"  FAIL: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

print("=== All imports OK - Starting uvicorn ===", flush=True)

import uvicorn
import os
port = int(os.environ.get("PORT", 10000))
uvicorn.run(server.app, host="0.0.0.0", port=port)
