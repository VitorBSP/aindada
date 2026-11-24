-- Stub do que o Supabase fornece e as migrações assumem. NÃO é o Supabase: só o mínimo para rodar as migrações e
-- os testes num Postgres comum (papéis, schema auth, auth.uid(), schema extensions, privilégios padrão).
drop role if exists anon; drop role if exists authenticated; drop role if exists service_role;
create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
grant usage on schema public to anon, authenticated, service_role;
create schema extensions;
do $$ begin execute format('alter database %I set search_path = "$user", public, extensions', current_database()); end $$;
create extension citext with schema extensions;
create schema auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text, created_at timestamptz default now());
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
-- O Supabase concede tudo nas tabelas e funções novas do schema public a estes papéis; as migrações revogam o que
-- não deve ficar.
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
