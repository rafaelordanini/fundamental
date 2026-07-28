#!/usr/bin/env bash
set -euo pipefail

if (( $# < 4 )); then
  echo "Uso: $0 <nome> <email> <mensagem> <arquivo> [arquivo ...]" >&2
  exit 2
fi

name=$1
email=$2
message=$3
shift 3
branch=${GITHUB_REF_NAME:-$(git branch --show-current)}

git config user.name "$name"
git config user.email "$email"
git add -- "$@"

if git diff --staged --quiet; then
  echo "Nenhuma alteração gerada para enviar."
  exit 0
fi

git commit -m "$message"

# Uma análise pode levar mais de uma hora. Nesse intervalo outro workflow pode
# atualizar main; nesse caso, reaplique somente o commit de dados e tente de
# novo, em vez de perder todo o resultado com um non-fast-forward.
for attempt in 1 2 3 4 5; do
  if git push origin "HEAD:${branch}"; then
    exit 0
  fi
  if (( attempt == 5 )); then
    echo "Falha ao enviar dados após ${attempt} tentativas." >&2
    exit 1
  fi
  echo "Branch avançou durante a execução; sincronizando (tentativa ${attempt}/5)."
  git fetch origin "$branch"
  git rebase -X theirs "origin/${branch}"
  sleep $((attempt * 2))
done
