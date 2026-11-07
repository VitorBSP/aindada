/* Conexão do simulador com o Supabase (ADR-0015, fase 2). Só liga com simulator-config.js preenchido.
   Conta anônima criada só quando o visitante pede. Dois e-mails opcionais e separados: o de login (entrar em outro
   aparelho) e o de avisos de pontuação (sim_contacts, privado).
   O apelido é a única identificação pública. Nenhuma função aqui lê ou mostra o e-mail de outra pessoa. */
(function () {
  "use strict";

  const LIBRARY_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js";
  const COMMUNITY_TTL_MS = 60000;
  const config = window.AINDA_DA_SIMULATOR || {};
  const enabled = Boolean(config.supabaseUrl && config.supabaseAnonKey);
  const competition = config.competition || "serie-a";
  let clientPromise = null;
  const communityCache = new Map();

  function loadLibrary() {
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = LIBRARY_URL;
      script.crossOrigin = "anonymous";
      script.onload = resolve;
      script.onerror = () => reject(new Error("biblioteca do Supabase indisponível"));
      document.head.appendChild(script);
    });
  }

  function client() {
    if (!enabled) return Promise.reject(new Error("simulador sem servidor"));
    if (!clientPromise) {
      clientPromise = loadLibrary().then(() => window.supabase.createClient(config.supabaseUrl, config.supabaseAnonKey, {
        auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, storageKey: "ainda-da-simulador-auth" },
      }));
      clientPromise.catch(() => { clientPromise = null; });
    }
    return clientPromise;
  }

  function check(result) {
    if (result.error) throw new Error(result.error.message || "erro no servidor");
    return result.data;
  }

  const returnUrl = () => location.href.split("#")[0] + "#/simular";

  async function currentUser() {
    const supabase = await client();
    const { data } = await supabase.auth.getSession();
    const user = data && data.session ? data.session.user : null;
    return user ? { id: user.id, anonymous: Boolean(user.is_anonymous), hasEmail: Boolean(user.email) } : null;
  }

  async function join() {
    const supabase = await client();
    const existing = await currentUser();
    if (existing) return existing;
    check(await supabase.auth.signInAnonymously());
    return currentUser();
  }

  async function linkEmail(email) {
    const supabase = await client();
    check(await supabase.auth.updateUser({ email }, { emailRedirectTo: returnUrl() }));
  }

  async function signInWithEmail(email) {
    const supabase = await client();
    check(await supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: false, emailRedirectTo: returnUrl() } }));
  }

  async function signOut() {
    const supabase = await client();
    check(await supabase.auth.signOut());
  }

  async function deleteAccount() {
    const supabase = await client();
    check(await supabase.rpc("sim_delete_me"));
    await supabase.auth.signOut();
  }

  async function profile() {
    const supabase = await client();
    const user = await currentUser();
    if (!user) return null;
    const rows = check(await supabase.from("sim_profiles").select("nickname, show_in_ranking").eq("user_id", user.id));
    return rows[0] || { nickname: null, show_in_ranking: false };
  }

  async function saveProfile(nickname, showInRanking) {
    const supabase = await client();
    const user = await currentUser();
    if (!user) throw new Error("entre primeiro");
    const row = { user_id: user.id, nickname: nickname || null, show_in_ranking: Boolean(nickname) && showInRanking };
    const result = await supabase.from("sim_profiles").upsert(row, { onConflict: "user_id" });
    if (result.error && result.error.code === "23505") throw new Error("esse apelido já está em uso");
    if (result.error && result.error.code === "23514") throw new Error("apelido com 3 a 20 letras, números, espaço, ponto, hífen ou _");
    check(result);
  }

  /* Payload no formato do banco (sim_lock_picks): a Classificação guarda a ordem; Vencedor e Placar exato guardam
     os palpites (os do usuário e os sorteados pelo modelo, que também valem pontos), a lista dos sorteados e a
     tabela final quando todos os jogos têm resultado. */
  function payloadOf(mode, entry, finalOrder) {
    if (mode === "classificacao") return { order: entry.order };
    const sampled = entry.sampled || {};
    const payload = { picks: { ...sampled, ...(entry.picks || {}) }, sampled: Object.keys(sampled).filter((id) => !(entry.picks || {})[id]) };
    if (finalOrder) payload.final_order = finalOrder;
    return payload;
  }

  /* Cria (sem serverId) ou atualiza uma simulação; devolve o ID e o que o servidor de fato guardou. */
  async function saveSimulation(season, mode, entry, serverId, finalOrder) {
    const supabase = await client();
    const user = await currentUser();
    if (!user) return null;
    const payload = payloadOf(mode, entry, finalOrder);
    const result = serverId
      ? await supabase.from("sim_simulations").update({ payload, assist: Boolean(entry.model) }).eq("id", serverId).select("id, payload")
      : await supabase.from("sim_simulations").insert({ user_id: user.id, competition, season, mode, payload, assist: Boolean(entry.model) }).select("id, payload");
    if (result.error && result.error.code === "P0001") throw new Error("limite de 3 simulações por modo no servidor");
    if (result.error && result.error.code === "22023") throw new Error("a ordem é impossível pela matemática ou está incompleta");
    const rows = check(result);
    return rows && rows[0] ? rows[0] : null;
  }

  async function deleteSimulation(serverId) {
    const supabase = await client();
    check(await supabase.from("sim_simulations").delete().eq("id", serverId));
  }

  /* O que o servidor guarda depois da trava: sim_lock_picks descarta palpites de jogos já travados. */
  async function seasonInfo(season) {
    const supabase = await client();
    const rows = check(await supabase.from("sim_seasons").select("classificacao_locks_at, final_at")
      .eq("competition", competition).eq("season", season));
    return rows[0] || null;
  }

  async function loadSimulations(season) {
    const supabase = await client();
    const user = await currentUser();
    if (!user) return [];
    return check(await supabase.from("sim_simulations").select("id, mode, payload, assist, created_at, updated_at")
      .eq("user_id", user.id).eq("competition", competition).eq("season", season).order("id"));
  }

  async function consensus(season) {
    const supabase = await client();
    return check(await supabase.rpc("sim_consensus", { p_competition: competition, p_season: season }));
  }

  /* E-mail para avisos de pontuação: tabela privada (só o dono lê), separada do login. */
  async function contact() {
    const supabase = await client();
    const user = await currentUser();
    if (!user) return null;
    const rows = check(await supabase.from("sim_contacts").select("email, notify").eq("user_id", user.id));
    return rows[0] || null;
  }

  async function saveContact(email, notify) {
    const supabase = await client();
    const user = await currentUser();
    if (!user) throw new Error("participe primeiro");
    const result = await supabase.from("sim_contacts").upsert({ user_id: user.id, email, notify }, { onConflict: "user_id" });
    if (result.error && result.error.code === "23514") throw new Error("e-mail inválido");
    check(result);
  }

  async function deleteContact() {
    const supabase = await client();
    const user = await currentUser();
    if (user) check(await supabase.from("sim_contacts").delete().eq("user_id", user.id));
  }

  async function community(season) {
    const cached = communityCache.get(season);
    if (cached && Date.now() - cached.at < COMMUNITY_TTL_MS) return cached.data;
    const supabase = await client();
    const data = check(await supabase.rpc("sim_community", { p_competition: competition, p_season: season }));
    communityCache.set(season, { at: Date.now(), data });
    return data;
  }

  async function ranking(season, mode) {
    const supabase = await client();
    return check(await supabase.rpc("sim_ranking", { p_competition: competition, p_season: season, p_mode: mode, p_limit: 100 }));
  }

  async function myScores(season) {
    const supabase = await client();
    if (!(await currentUser())) return [];
    return check(await supabase.rpc("sim_my_scores", { p_competition: competition, p_season: season }));
  }

  window.SimulatorCloud = {
    enabled, currentUser, join, linkEmail, signInWithEmail, signOut, deleteAccount, profile, saveProfile,
    saveSimulation, deleteSimulation, seasonInfo, loadSimulations, community, consensus, ranking, myScores,
    contact, saveContact, deleteContact,
  };
})();
