# devops/diagnostic.py
"""Diagnostic complet d'un projet (Render + env vars critiques)."""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(".secrets.env")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contexts import ALL_PROJECTS, get_context  # noqa: E402


def run(project):
    print(f"\n🔍 DIAGNOSTIC COMPLET — {project.upper()}")
    ctx = get_context(project)
    ctx.run_diagnostic()

    print("\n2. Variables critiques côté shell :")
    important = {
        "kenbot": ["RENDER_API_KEY", "SUPABASE_URL", "TWILIO_ACCOUNT_SID", "GITHUB_TOKEN"],
        "luxura": ["RENDER_API_KEY", "SUPABASE_URL"],
        "calcauto": ["RENDER_API_KEY", "GOOGLE_VISION_API_KEY", "SUPABASE_URL"],
    }.get(project, ["RENDER_API_KEY"])
    for var in important:
        v = os.getenv(var)
        print(f"   {var}: {'✅ Présente' if v else '❌ Manquante'}")
    print("\n✅ Diagnostic terminé.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project", choices=list(ALL_PROJECTS.keys()), default="kenbot"
    )
    args = parser.parse_args()
    run(args.project)


if __name__ == "__main__":
    main()
