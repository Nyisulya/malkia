#!/usr/bin/env python3
"""
Malkia Cargo Wave - Push to GitHub Utility
Usage:
    python push_to_github.py <YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>
Or:
    python push_to_github.py
    (and enter token securely when prompted)
"""
import sys
import getpass
from dulwich import porcelain
from dulwich.repo import Repo

def main():
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    else:
        print("=" * 60)
        print("  MALKIA CARGO WAVE - GITHUB PUSH")
        print("=" * 60)
        token = getpass.getpass("Enter your GitHub Personal Access Token (PAT): ").strip()

    if not token:
        print("[ERROR] No GitHub token provided.")
        sys.exit(1)

    repo = Repo('.')
    
    # Stage and commit any latest changes safely (NEVER stage .env, db.sqlite3, .venv, media, or scratch)
    print("[1/3] Checking for latest changes (excluding .env, db.sqlite3, and secrets)...")
    FORBIDDEN_PATTERNS = ('.env', 'db.sqlite3', '.sqlite3', '.venv', 'venv', 'media', 'staticfiles', 'scratch', '__pycache__')
    st = porcelain.status(repo)
    safe_paths = []
    for p in st.unstaged:
        p_str = p.decode('utf-8', errors='ignore')
        if p_str == '.env.example' or not any(bad in p_str for bad in FORBIDDEN_PATTERNS):
            safe_paths.append(p_str)
    for p in st.untracked:
        p_str = p.decode('utf-8', errors='ignore') if isinstance(p, bytes) else str(p)
        if p_str in ('.env.example', 'delete_second_job.py') or (not any(bad in p_str for bad in FORBIDDEN_PATTERNS) and ('core' in p_str or 'templates' in p_str or 'website' in p_str or 'static' in p_str or 'deploy' in p_str or p_str.endswith('.py'))):
            safe_paths.append(p_str)
    if safe_paths:
        porcelain.add(repo, paths=safe_paths)
    try:
        st_after = porcelain.status(repo)
        if st_after.staged['add'] or st_after.staged['modify'] or st_after.staged['delete']:
            porcelain.commit(
                repo,
                message=b"Production release: Resend Email, SMS Gate, SEO Engine, Costing Ledger & Workflow updates (zero secrets)",
                author=b"Nyisulya <nyisulya@users.noreply.github.com>",
                committer=b"Nyisulya <nyisulya@users.noreply.github.com>"
            )
            print("[2/3] Committed latest changes.")
        else:
            print("[2/3] Working tree clean, all changes already committed.")
    except Exception as e:
        print(f"[2/3] Commit status: {e}")

    remote_url = f"https://{token}@github.com/Nyisulya/malkia.git"
    print("[3/3] Pushing to GitHub (https://github.com/Nyisulya/malkia.git)...")
    try:
        porcelain.push(repo, remote_url, refspecs=["refs/heads/master:refs/heads/main"])
        print("\n" + "=" * 60)
        print("[SUCCESS] Kod zimesukumwa kikamilifu kwenye GitHub!")
        print("URL: https://github.com/Nyisulya/malkia")
        print("=" * 60)
    except Exception as e:
        # Fallback to push to master if main branch isn't standard
        try:
            porcelain.push(repo, remote_url, refspecs=["refs/heads/master:refs/heads/master"])
            print("\n" + "=" * 60)
            print("[SUCCESS] Kod zimesukumwa kikamilifu kwenye branch ya master!")
            print("URL: https://github.com/Nyisulya/malkia")
            print("=" * 60)
        except Exception as e2:
            print(f"\n[ERROR] Push failed: {e2}")
            print("Hakikisha token yako ina ruhusa ya 'repo' (write access).")

if __name__ == '__main__':
    main()

