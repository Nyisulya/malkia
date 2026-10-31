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
    
    # Stage and commit any latest changes
    print("[1/3] Checking for latest changes...")
    porcelain.add(repo)
    try:
        porcelain.commit(
            repo,
            message=b"Update: Production release with clean credentials and .env security",
            author=b"Nyisulya <nyisulya@users.noreply.github.com>",
            committer=b"Nyisulya <nyisulya@users.noreply.github.com>"
        )
        print("[2/3] Committed latest changes.")
    except Exception:
        print("[2/3] Working tree clean, nothing new to commit.")

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

