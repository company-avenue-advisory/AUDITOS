#!/usr/bin/env bash
# Self-check for scripts/deploy_remote.sh's failure handling — regression
# tests for two real production incidents:
#   1. `deploy_and_check` is called as `if deploy_and_check ...; then`,
#      which disables `set -e` for everything inside it, so a failing
#      `git checkout` was silently ignored and the job reported false
#      success while actually redeploying nothing.
#   2. The dirty-tree guard added to fix #1 used plain `git status
#      --porcelain`, which also flags *untracked* files -- so a harmless
#      leftover backup file (which never actually blocks `git checkout`)
#      made every deploy refuse to proceed.
#
# Mocks git/docker as shell functions so this runs anywhere, no droplet
# or network needed. Run: bash scripts/test_deploy_remote.sh
set -e
cd "$(dirname "$0")/.."
FAILURES=0

run_case() {
  local name="$1" git_checkout_behavior="$2" git_dirty="$3" git_untracked="$4"
  local out
  out=$(
    git() {
      case "$1" in
        rev-parse) echo "0000000000000000000000000000000000000000" ;;
        status)
          local untracked_excluded=0
          for a in "$@"; do [ "$a" = "--untracked-files=no" ] && untracked_excluded=1; done
          [ "$GIT_DIRTY" = "1" ] && echo " M some_file.py"
          [ "$untracked_excluded" = "0" ] && [ "$GIT_UNTRACKED" = "1" ] && echo "?? some_backup_file"
          ;;
        fetch) return 0 ;;
        checkout) [ "$GIT_CHECKOUT_FAIL" = "1" ] && return 1 || return 0 ;;
      esac
    }
    docker() {
      if [ "$1" = "compose" ]; then return 0; fi
      # `docker inspect` — report healthy/running immediately.
      case "$*" in
        *auditos-backend-1*) echo "healthy" ;;
        *auditos-worker-1*) echo "running" ;;
      esac
    }
    export -f git docker
    GIT_CHECKOUT_FAIL="$git_checkout_behavior" GIT_DIRTY="$git_dirty" GIT_UNTRACKED="$git_untracked" DEPLOY_DIR="$PWD" \
      bash scripts/deploy_remote.sh deadbeefdeadbeefdeadbeefdeadbeefdeadbeef 2>&1
  )
  local exit_code=$?
  echo "$out"
  return $exit_code
}

echo "--- case: clean tree, checkout succeeds -> expect job succeeds ---"
if run_case clean 0 0 0 > /tmp/out1.txt; then
  echo "PASS: succeeded as expected"
else
  echo "FAIL: expected success"; FAILURES=$((FAILURES+1))
fi
cat /tmp/out1.txt

echo
echo "--- case: tracked dirty tree -> expect job FAILS (not a false success) ---"
if run_case dirty 0 1 0 > /tmp/out2.txt; then
  echo "FAIL: job reported success despite a dirty working tree — incident #1 is back."
  FAILURES=$((FAILURES+1))
else
  echo "PASS: correctly failed on tracked dirty tree"
fi
cat /tmp/out2.txt

echo
echo "--- case: checkout fails -> expect job FAILS (not a false success) ---"
if run_case checkout_fail 1 0 0 > /tmp/out3.txt; then
  echo "FAIL: job reported success despite git checkout failing — incident #1 is back."
  FAILURES=$((FAILURES+1))
else
  echo "PASS: correctly failed on checkout failure"
fi
cat /tmp/out3.txt

echo
echo "--- case: only an untracked file present -> expect job SUCCEEDS (doesn't block a real checkout) ---"
if run_case untracked_only 0 0 1 > /tmp/out4.txt; then
  echo "PASS: correctly ignored an untracked file"
else
  echo "FAIL: job refused to deploy over a harmless untracked file — incident #2 is back."
  FAILURES=$((FAILURES+1))
fi
cat /tmp/out4.txt

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "All deploy_remote.sh failure-handling checks passed."
  exit 0
else
  echo "$FAILURES check(s) failed."
  exit 1
fi
