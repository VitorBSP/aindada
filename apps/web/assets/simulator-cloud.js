/* Conexão do simulador com o Supabase (ADR-0015, fase 2). Só liga com simulator-config.js preenchido.
   Conta anônima criada só quando o visitante pede. Dois e-mails opcionais e separados: o de login (entrar em outro
   aparelho) e o de avisos de pontuação (sim_contacts, privado).
   O apelido é a única identificação pública. Nenhuma função aqui lê ou mostra o e-mail de outra pessoa. */
(function () {
  "use strict";

  /* Versão exata e hash de integridade (SRI) do arquivo dist/umd/supabase.js do pacote npm 2.45.4, conferido com o
     sha512 que o registro do npm publica para o pacote. Se o jsDelivr servir outro conteúdo, o navegador não executa o
     arquivo e o simulador continua só no aparelho. Trocar de versão = trocar a URL e o hash juntos. */
  const LIBRARY_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js";
  const LIBRARY_INTEGRITY = "sha384-0w2KAL2YHP6wKOkUDzkCDGgVvfmHnj02DHeQ6XcHOgTfFsGyonKOpShMH1x6nk9o";
  /* Cloudflare Turnstile: o script não aceita SRI (a Cloudflare o atualiza sem mudar a URL) e só carrega se houver
     turnstileSiteKey em simulator-config.js, ao clicar em Participar ou pedir o link de entrada. */
  const TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
  const COMMUNITY_TTL_MS = 60000;
  const config = window.AINDA_DA_SIMULATOR || {};
  const enabled = Boolean(config.supabaseUrl && config.supabaseAnonKey);
  const captchaEnabled = enabled && Boolean(config.turnstileSiteKey);
  const competition = config.competition || "serie-a";
  let clientPromise = null;
  let turnstilePromise = null;
  const communityCache = new Map();

  function loadScript(src, integrity) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      if (integrity) script.integrity = integrity;
      script.crossOrigin = "anonymous";
      script.async = true;
      script.onload = resolve;
      script.onerror = () => { script.remove(); reject(new Error("arquivo indisponível ou diferente do esperado")); };
      document.head.appendChild(script);
    });
  }

  function loadLibrary() {
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    return loadScript(LIBRARY_URL, LIBRARY_INTEGRITY).catch(() => { throw new Error("biblioteca do Supabase indisponível"); });
  }

  /* ---- Apelidos: filtro leve e honesto. Pega palavrões, ofensas comuns e nomes que imitam o site, com acentos,
     números no lugar de letras (c4r4lh0) e letras repetidas. Não pega tudo: o que passar, a pessoa denuncia no
     repositório. A mesma lista está na sugestão de trava do banco (infrastructure/supabase/sugestoes/). ---- */
  const BLOCKED_NICKNAMES = {
    // palavra inteira (curtas, para não barrar "cuca" nem "computador")
    exact: ["cu", "cuzao", "fdp", "pqp", "vsf", "tnc", "krl", "crl", "pnc", "bicha", "bixa", "bichona", "viado", "viada",
      "viadao", "veado", "fag", "nazi", "nazista"],
    // começo de palavra
    prefix: ["puta", "puto", "merda", "foda", "fode", "foder", "fuder", "xota", "xoxota", "corno", "corna", "otari",
      "vagabund", "babac", "idiota", "imbecil", "retardad", "traveco", "sapatao", "fuck", "shit", "bitch", "admin",
      "moderador", "suporte", "oficial", "staff"],
    // em qualquer lugar, mesmo grudado em outras letras
    contains: ["caralh", "porra", "bucet", "arromb", "estupr", "pedofil", "hitler", "putaria", "viadinh", "filhadaput",
      "filhodaput", "nigger", "nigga", "aindada", "supabase"],
  };
  const LEET = { 0: "o", 1: "i", 3: "e", 4: "a", 5: "s", 7: "t", 8: "b" };
  const normalizeNickname = (text) => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[0134578]/g, (digit) => LEET[digit]).replace(/([a-z])\1{2,}/g, "$1$1");

  /* Devolve o motivo da recusa ou "" se o apelido passa. Mesmas regras de formato do banco (sim_profiles.nickname). */
  function nicknameProblem(nickname) {
    const value = String(nickname || "").trim();
    if (!value) return "";
    if (!/^[A-Za-zÀ-ÖØ-öø-ÿ0-9_. -]{3,20}$/.test(value)) return "apelido com 3 a 20 letras, números, espaço, ponto, hífen ou _";
    const normal = normalizeNickname(value);
    const words = normal.split(/[^a-z]+/).filter(Boolean);
    const compact = words.join("");
    const hit = BLOCKED_NICKNAMES.exact.some((term) => words.includes(term))
      || BLOCKED_NICKNAMES.prefix.some((term) => words.some((word) => word.startsWith(term)))
      || BLOCKED_NICKNAMES.contains.some((term) => compact.includes(term));
    return hit ? "esse apelido parece ofensivo ou parece falar em nome do site; escolha outro" : "";
  }

  /* ---- CAPTCHA (Turnstile), opcional. Sem turnstileSiteKey, devolve undefined e o fluxo segue como antes. ---- */
  function loadTurnstile() {
    if (window.turnstile) return Promise.resolve();
    if (!turnstilePromise) {
      turnstilePromise = loadScript(TURNSTILE_URL, "").catch(() => {
        turnstilePromise = null;
        throw new Error("verificação contra robôs indisponível");
      });
    }
    return turnstilePromise;
  }

  async function captchaToken(container, action) {
    if (!captchaEnabled) return undefined;
    await loadTurnstile();
    const host = container || document.body;
    const slot = document.createElement("div");
    host.appendChild(slot);
    return new Promise((resolve, reject) => {
      let widget = null;
      const finish = (callback) => (value) => {
        try { if (widget !== null) window.turnstile.remove(widget); } catch (error) { /* widget já removido */ }
        slot.remove();
        callback(value);
      };
      widget = window.turnstile.render(slot, {
        sitekey: config.turnstileSiteKey,
        action,
        language: "pt-br",
        appearance: "interaction-only",
        callback: finish(resolve),
        "error-callback": finish(() => reject(new Error("a verificação contra robôs falhou; tente de novo"))),
        "expired-callback": finish(() => reject(new Error("a verificação contra robôs expirou; tente de novo"))),
      });
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

  async function join(captchaContainer) {
    const supabase = await client();
    const existing = await currentUser();
    if (existing) return existing;
    const token = await captchaToken(captchaContainer, "participar");
    check(await supabase.auth.signInAnonymously(token ? { options: { captchaToken: token } } : undefined));
    return currentUser();
  }

  async function linkEmail(email) {
    const supabase = await client();
    check(await supabase.auth.updateUser({ email }, { emailRedirectTo: returnUrl() }));
  }

  async function signInWithEmail(email, captchaContainer) {
    const supabase = await client();
    const token = await captchaToken(captchaContainer, "entrar");
    const options = { shouldCreateUser: false, emailRedirectTo: returnUrl() };
    if (token) options.captchaToken = token;
    check(await supabase.auth.signInWithOtp({ email, options }));
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
    /* Apelido que já está salvo não passa de novo pelo filtro: conta antiga não quebra ao mudar só o ranking. */
    const current = check(await supabase.from("sim_profiles").select("nickname").eq("user_id", user.id));
    const unchanged = current[0] && current[0].nickname === (nickname || null);
    const problem = unchanged ? "" : nicknameProblem(nickname);
    if (problem) throw new Error(problem);
    const row = { user_id: user.id, nickname: nickname || null, show_in_ranking: Boolean(nickname) && showInRanking };
    const result = await supabase.from("sim_profiles").upsert(row, { onConflict: "user_id" });
    if (result.error && result.error.code === "23505") throw new Error("esse apelido já está em uso");
    if (result.error && result.error.code === "23514") throw new Error("apelido com 3 a 20 letras, números, espaço, ponto, hífen ou _");
    if (result.error && result.error.code === "AIN01") throw new Error("esse apelido parece ofensivo ou parece falar em nome do site; escolha outro");
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
      ? await supabase.from("sim_simulations").update({ payload, assist: Boolean(entry.model) }).eq("id", serverId).select("id, payload, created_at")
      : await supabase.from("sim_simulations").insert({ user_id: user.id, competition, season, mode, payload, assist: Boolean(entry.model) }).select("id, payload, created_at");
    if (result.error && result.error.code === "P0001") {
      throw new Error(/fechada/.test(result.error.message || "") ? "esta simulação está fechada: um jogo começou depois que ela foi salva" : "limite de 10 simulações por pessoa até o próximo jogo");
    }
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
    enabled, captchaEnabled, nicknameProblem, BLOCKED_NICKNAMES, LIBRARY_URL, LIBRARY_INTEGRITY, currentUser, join, linkEmail, signInWithEmail, signOut, deleteAccount, profile, saveProfile,
    saveSimulation, deleteSimulation, seasonInfo, loadSimulations, community, consensus, ranking, myScores,
    contact, saveContact, deleteContact,
  };
})();
