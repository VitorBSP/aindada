#!/usr/bin/env bash
# Roda as migrações 0001..0007 e os testes de SQL num Postgres descartável (nunca no Supabase real).
#
# Uso:
#   infrastructure/supabase/tests/run.sh                # sobe um cluster temporário (precisa dos binários do Postgres)
#   TEST_DATABASE_URL=postgresql://... run.sh           # usa um banco que já existe; o nome tem de terminar em _test
#
# O banco recebe primeiro um "stub" do Supabase (papéis anon/authenticated/service_role, auth.users, auth.uid()).
# Saída em formato TAP; o código de saída é diferente de zero se qualquer teste falhar.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
migrations="$here/../migrations"
cleanup=""

if [[ -n "${TEST_DATABASE_URL:-}" ]]; then
  database="${TEST_DATABASE_URL##*/}"; database="${database%%\?*}"
  if [[ "$database" != *_test ]]; then
    echo "recusado: o banco '$database' não termina em _test (este script apaga e recria o esquema public)" >&2
    exit 2
  fi
  psql_url="$TEST_DATABASE_URL"
else
  pg_bin="${PG_BIN:-$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1)}"
  [[ -x "$pg_bin/initdb" ]] || { echo "binários do Postgres não encontrados (defina PG_BIN)" >&2; exit 2; }
  work="$(mktemp -d)"
  port="${PGTESTPORT:-54329}"
  as_pg() { if [[ "$(id -u)" == 0 ]]; then runuser -u postgres -- "$@"; else "$@"; fi; }
  [[ "$(id -u)" == 0 ]] && chown postgres "$work"
  as_pg "$pg_bin/initdb" -D "$work/data" -A trust -U postgres >/dev/null
  as_pg "$pg_bin/pg_ctl" -D "$work/data" -o "-p $port -k $work -c listen_addresses=''" -l "$work/log" -w start >/dev/null
  cleanup="as_pg $pg_bin/pg_ctl -D $work/data -m immediate stop >/dev/null; rm -rf $work"
  trap 'eval "$cleanup"' EXIT
  as_pg "$pg_bin/createdb" -h "$work" -p "$port" -U postgres aindada_test
  psql_url="postgresql://postgres@/aindada_test?host=$work&port=$port"
  echo "# Postgres: $("$pg_bin/postgres" --version)"
fi

run() { psql "$psql_url" -X -q -o /dev/null -v ON_ERROR_STOP=1 -f "$1" 2>&1 | sed -e '/^psql:.*NOTICE:  /s///' -e 's/^NOTICE:  //'; return "${PIPESTATUS[0]}"; }
apply() { echo "# aplicando $(basename "$1")"; psql "$psql_url" -X -q -v ON_ERROR_STOP=1 -f "$1" >/dev/null; }

psql "$psql_url" -X -q -v ON_ERROR_STOP=1 -c "drop schema if exists public cascade; create schema public; drop schema if exists auth cascade; drop schema if exists t cascade;" >/dev/null 2>&1 || true
run "$here/00_stub_supabase.sql" >/dev/null
# o search_path do banco só vale em sessões novas, então cada psql abaixo já o recebe
run "$here/01_tap.sql" >/dev/null

for file in "$migrations"/000[1-6]_*.sql; do apply "$file"; done
run "$here/05_fixtures.sql" >/dev/null
run "$here/06_ataque.sql" >/dev/null
echo "# --- Medida antes da 0007 (consenso da 0004) ---"
run "$here/50_ataque_antes.sql"

for file in "$migrations"/0007_*.sql; do apply "$file"; done

status=0
for test_file in "$here"/[1-4]0_*.sql "$here"/51_*.sql; do
  echo "# --- $(basename "$test_file") ---"
  run "$test_file" || status=1
done
[[ -n "${EXTRA_SQL:-}" ]] && psql "$psql_url" -X -f "$EXTRA_SQL" 2>&1
echo "# --- resumo ---"
psql "$psql_url" -X -q -t -A -c "select 'testes: ' || count(*) || ', falhas: ' || count(*) filter (where not passed) from t.results" || status=1
failures="$(psql "$psql_url" -X -q -t -A -c "select count(*) from t.results where not passed")"
[[ "$failures" == 0 && "$status" == 0 ]]
