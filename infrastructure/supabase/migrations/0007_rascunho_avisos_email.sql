-- RASCUNHO, não aplicar.
-- ADR-0016 (proposta). Não foi executado em nenhum Postgres e depende de decisões do dono (ver o ADR).
-- Numeração: 0005 e 0006 já existem; este rascunho usa 0007. Renomear para 0007_simulador_avisos_email.sql
-- (sem o cabeçalho) só depois da aprovação do dono e da revisão dos Agentes 00 e 06.
--
-- Caminho recomendado (A): o aviso só vai para o e-mail CONFIRMADO do Supabase Auth (auth.users.email_confirmed_at).
-- A confirmação é feita pelo próprio Auth (link enviado pelo SMTP configurado no projeto). Não há tabela de tokens
-- de confirmação. A lista de envio passa a ler auth.users e ignora o e-mail digitado em sim_contacts.
-- O caminho alternativo (B, tokens próprios) está comentado no fim do arquivo.

-- ---------------------------------------------------------------- 1. Descadastro e controle de envio

alter table public.sim_contacts alter column email drop not null;   -- o e-mail de verdade fica em auth.users
alter table public.sim_contacts add column unsubscribe_token uuid not null default gen_random_uuid();
create unique index sim_contacts_unsubscribe_token_key on public.sim_contacts (unsubscribe_token);

-- O que já foi avisado, para não repetir. Só a chave de serviço lê e escreve (sem policy, RLS ligada).
create table public.sim_notification_log (
  user_id uuid not null references auth.users (id) on delete cascade,
  competition text not null,
  season int not null,
  kind text not null check (kind in ('pontuacao')),
  last_sent_at timestamptz not null default now(),
  last_fingerprint text not null,        -- hash dos pontos enviados; mudou, avisa de novo
  primary key (user_id, competition, season, kind)
);
alter table public.sim_notification_log enable row level security;
revoke all on public.sim_notification_log from anon, authenticated;
grant select, insert, update on public.sim_notification_log to service_role;

-- ---------------------------------------------------------------- 2. Lista de envio (substitui a da 0003)

drop function public.sim_notification_list(text, int);
create function public.sim_notification_list(p_competition text, p_season int)
returns table (email text, nickname text, unsubscribe_token uuid, user_id uuid,
               simulation_id bigint, mode text, points int, max_points int)
language sql stable security definer set search_path = public, auth as $$
  select u.email::text, p.nickname::text, c.unsubscribe_token, c.user_id, sc.id, sc.mode, sc.points, sc.max_points
  from sim_contacts c
  join auth.users u on u.id = c.user_id
  left join sim_profiles p on p.user_id = c.user_id
  join sim_scores sc on sc.user_id = c.user_id and sc.competition = p_competition and sc.season = p_season
  where c.notify
    and u.email_confirmed_at is not null          -- só e-mail confirmado
    and not coalesce(u.is_anonymous, false)
  order by u.email, sc.mode, sc.id;
$$;
revoke all on function public.sim_notification_list(text, int) from public, anon, authenticated;
grant execute on function public.sim_notification_list(text, int) to service_role;

-- ---------------------------------------------------------------- 3. Descadastro por link (sem login)

create function public.sim_unsubscribe(p_token uuid)
returns boolean
language plpgsql security definer set search_path = public as $$
declare changed int;
begin
  update sim_contacts set notify = false where unsubscribe_token = p_token and notify;
  get diagnostics changed = row_count;
  return changed > 0;
end;
$$;
revoke all on function public.sim_unsubscribe(uuid) from public;
grant execute on function public.sim_unsubscribe(uuid) to anon, authenticated;

-- sim_delete_me (0001) já apaga auth.users; sim_contacts e sim_notification_log saem por "on delete cascade".

-- ================================================================ ALTERNATIVA B (tokens próprios), não aplicar junto
-- Só se o dono quiser avisar um e-mail diferente do e-mail de login.
--
-- alter table public.sim_contacts add column confirmed_at timestamptz;
-- alter table public.sim_contacts add column email_pending text;
--
-- create table public.sim_contact_tokens (
--   token_hash text primary key,                         -- sha-256 do token; o token em si só vai no e-mail
--   user_id uuid not null references auth.users (id) on delete cascade,
--   email text not null,
--   created_at timestamptz not null default now(),
--   expires_at timestamptz not null default now() + interval '24 hours',
--   used_at timestamptz
-- );
-- alter table public.sim_contact_tokens enable row level security;     -- sem policy: só funções security definer
-- revoke all on public.sim_contact_tokens from anon, authenticated;
--
-- sim_request_contact_confirmation(p_email): exige conta com participação; no máximo 3 pedidos por conta e por
--   24 h e 1 por minuto; grava o hash; quem envia o e-mail é o job/Edge Function (o banco não envia).
-- sim_confirm_contact(p_token): anon; confere hash, validade e used_at; grava confirmed_at e email; marca used_at.
-- A lista de envio exigiria confirmed_at is not null e usaria sim_contacts.email.
