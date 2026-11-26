-- SUGESTÃO, não é migração: trava de apelidos ofensivos no banco, igual ao filtro do navegador
-- (nicknameProblem em apps/web/assets/simulator-cloud.js). Fica fora de migrations/ de propósito: o dono decide se
-- aplica e quando, e a numeração definitiva entra quando virar migração.
--
-- Não quebra contas existentes: o gatilho só confere o apelido quando ele é criado ou MUDA. Quem já tem um apelido
-- que cairia no filtro continua com ele (e pode mudar só o "Aparecer no ranking"); a consulta do fim lista esses casos
-- para revisão manual. Recusa com SQLSTATE AIN01, que o simulator-cloud.js traduz para a mensagem do site.
--
-- A lista de termos é a mesma do navegador (tests/unit/test_simulator_cloud_js.py confere). Normalização igual: sem
-- acento, minúsculas, 0134578 → oieastb, letra repetida 3+ vezes vira 2.
-- Supõe banco em UTF8 (o do Supabase é): em SQL_ASCII, o translate dos acentos sai errado.
--
-- Conferido num Postgres 16 descartável (UTF8) com as migrações 0001 a 0007: recusa "C4R4LH0 fc", "Pútaaaa" e
-- "cu de mae"; aceita "Computador" e "Cuca 10"; conta antiga com apelido ruim muda o ranking e regrava o mesmo
-- apelido, mas não troca por outro ruim; reaplicar o arquivo não dá erro.

create table if not exists public.sim_blocked_terms (
  term text primary key check (term ~ '^[a-z]+$'),
  kind text not null check (kind in ('exact', 'prefix', 'contains'))
);
alter table public.sim_blocked_terms enable row level security;
revoke all on public.sim_blocked_terms from public, anon, authenticated;

insert into public.sim_blocked_terms (term, kind)
select term, 'exact' from unnest(array['cu', 'cuzao', 'fdp', 'pqp', 'vsf', 'tnc', 'krl', 'crl', 'pnc', 'bicha', 'bixa',
  'bichona', 'viado', 'viada', 'viadao', 'veado', 'fag', 'nazi', 'nazista']) as term
union all
select term, 'prefix' from unnest(array['puta', 'puto', 'merda', 'foda', 'fode', 'foder', 'fuder', 'xota', 'xoxota',
  'corno', 'corna', 'otari', 'vagabund', 'babac', 'idiota', 'imbecil', 'retardad', 'traveco', 'sapatao', 'fuck', 'shit',
  'bitch', 'admin', 'moderador', 'suporte', 'oficial', 'staff']) as term
union all
select term, 'contains' from unnest(array['caralh', 'porra', 'bucet', 'arromb', 'estupr', 'pedofil', 'hitler', 'putaria',
  'viadinh', 'filhadaput', 'filhodaput', 'nigger', 'nigga', 'aindada', 'supabase']) as term
on conflict (term) do update set kind = excluded.kind;

create or replace function public.sim_normalize_nickname(p_nickname text) returns text
language sql immutable set search_path = public as $$
  select regexp_replace(
    translate(lower(coalesce(p_nickname, '')),
      'áàâãäåéèêëíìîïóòôõöúùûüçñý0134578',
      'aaaaaaeeeeiiiiooooouuuucnyoieastb'),
    '([a-z])\1{2,}', '\1\1', 'g')
$$;

create or replace function public.sim_nickname_blocked(p_nickname text) returns boolean
language sql stable set search_path = public as $$
  with normal as (select public.sim_normalize_nickname(p_nickname) as value),
  words as (select word from normal, regexp_split_to_table(normal.value, '[^a-z]+') as word where word <> ''),
  compact as (select coalesce(string_agg(word, ''), '') as value from words)
  select exists (
    select 1 from public.sim_blocked_terms blocked
    where (blocked.kind = 'exact' and exists (select 1 from words where word = blocked.term))
       or (blocked.kind = 'prefix' and exists (select 1 from words where left(word, length(blocked.term)) = blocked.term))
       or (blocked.kind = 'contains' and position(blocked.term in (select value from compact)) > 0)
  )
$$;

create or replace function public.sim_check_nickname() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.nickname is not null
     and (tg_op = 'INSERT' or new.nickname is distinct from old.nickname)
     and public.sim_nickname_blocked(new.nickname) then
    raise exception 'apelido recusado pelo filtro' using errcode = 'AIN01';
  end if;
  return new;
end;
$$;

revoke all on function public.sim_normalize_nickname(text) from public, anon, authenticated;
revoke all on function public.sim_nickname_blocked(text) from public, anon, authenticated;
revoke all on function public.sim_check_nickname() from public, anon, authenticated;

drop trigger if exists sim_check_nickname on public.sim_profiles;
create trigger sim_check_nickname before insert or update of nickname on public.sim_profiles
  for each row execute function public.sim_check_nickname();

-- Revisão manual (rodar à parte, como dono): apelidos que já existem e cairiam no filtro. Nada é apagado.
-- select user_id, nickname, show_in_ranking from public.sim_profiles where public.sim_nickname_blocked(nickname);
