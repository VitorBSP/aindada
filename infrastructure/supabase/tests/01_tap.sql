-- Mini-biblioteca de asserts (TAP). Sem pgTAP para rodar em qualquer Postgres; resultados em t.results.
create schema t;
create table t.results (n serial primary key, passed boolean not null, description text not null);
create function t.ok(p_condition boolean, p_description text) returns boolean language plpgsql as $$
declare ok boolean := coalesce(p_condition, false); n int;
begin
  insert into t.results (passed, description) values (ok, p_description) returning t.results.n into n;
  raise notice '% % - %', case when ok then 'ok' else 'not ok' end, n, p_description;
  return ok;
end $$;
create function t.is(p_got anyelement, p_want anyelement, p_description text) returns boolean language plpgsql as $$
declare ok boolean := p_got is not distinct from p_want;
begin
  perform t.ok(ok, p_description);
  if not ok then raise notice '#   obtido:   %', p_got; raise notice '#   esperado: %', p_want; end if;
  return ok;
end $$;
-- Roda um comando e confere o SQLSTATE do erro (ou ausência de erro, com null).
create function t.throws(p_sql text, p_sqlstate text, p_description text) returns boolean language plpgsql as $$
declare got text;
begin
  begin execute p_sql; exception when others then got := sqlstate; end;
  return t.is(got, p_sqlstate, p_description);
end $$;
-- Executa uma consulta que devolve um número como o papel dado (com auth.uid() = sub); devolve -1 se der erro.
create function t.count_as(p_role text, p_sub uuid, p_sql text) returns bigint language plpgsql as $$
declare n bigint;
begin
  perform set_config('request.jwt.claim.sub', coalesce(p_sub::text, ''), true);
  begin
    execute format('set local role %I', p_role);
    execute p_sql into n;
    reset role;
  exception when others then
    reset role; return -1;
  end;
  return n;
end $$;
-- Executa um comando como o papel dado e devolve o SQLSTATE do erro (null se funcionou).
create function t.error_as(p_role text, p_sub uuid, p_sql text) returns text language plpgsql as $$
declare got text;
begin
  perform set_config('request.jwt.claim.sub', coalesce(p_sub::text, ''), true);
  begin
    execute format('set local role %I', p_role);
    execute p_sql;
    reset role;
  exception when others then
    got := sqlstate; reset role;
  end;
  return got;
end $$;
