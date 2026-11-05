# ADR-0014 — Escudos oficiais sem licença livre (risco aceito)

- Status: **aceito pelo dono do produto** (2026-11-04).
- Responsáveis: Agente 00 (decisão), 01 (coleta e proveniência), 08 (forma, D-044), 05 (sites), 06 (validação),
  07 (checagem do artefato).
- Origem: pedido do dono do produto (chat, 2026-11-04): "não tem nenhum jeito de buscar esses símbolos em outros
  lugares? [...] até a própria wikipédia usa os símbolos". Diante das opções (aceitar o risco, pedir autorização
  aos clubes ou manter só os livres), a resposta foi "Aceito o risco".

## Contexto

Até aqui valia a D-028: só escudos em domínio público no Wikimedia Commons; sem versão livre, marcador com a sigla.
Isso deixava Corinthians, Vasco e Bragantino sem escudo na Série A, todos os clubes da Premier League e quase
todos da LaLiga. Os termos lidos em 2026-11-04 não dão licença a terceiros:

- football-data.org (seção 9.2): "All graphics, including team logos [...] are copyrighted by their legal owner.
  You'll have to obtain consent from the respective owners";
- TheSportsDB: a licença Creative Commons cobre só a arte própria, não logos de terceiros;
- Wikipédia em inglês: os logos não livres aparecem lá como uso justo, que vale só dentro da Wikipédia.

## Decisão

1. Ordem por time: escudo livre (Commons, domínio público ou CC0) → escudo oficial (arquivo da infobox do artigo
   da Wikipédia em inglês) → marcador com a sigla na cor oficial (sem artigo ou sem imagem).
2. Uso do escudo oficial só para identificar o time ao lado do nome: miniatura de 250 px da API da Wikipédia (o pedido é de 128 px;
   a API entrega a miniatura padrão), exibida entre 16 e 28 px, sem alteração de forma ou cor,
   sem uso como marca do AInda dá? e sem sugerir apoio ou relação com o clube.
3. Projeto gratuito, sem anúncios e sem venda. Se isso mudar, esta decisão é revista antes.
4. Rodapé de cada site: aviso de marca registrada e link para pedir a retirada (issues do repositório). Pedido de
   clube, liga ou dono da marca é atendido sem discussão na publicação seguinte, trocando o escudo pelo marcador.
5. Proveniência por arquivo (`data/reference/crests_provenance_<competição>.json`): arquivo de origem, página do
   arquivo, licença declarada, SHA-256 e data; `license_status` diz se é livre ou oficial (ADR-0014).
6. A checagem do artefato (`check_site_artifact.py`) deixa de proibir os três escudos da Série A e passa a exigir
   que todo arquivo de escudo esteja no manifesto da pasta, ou seja, que tenha passado pela coleta.
7. Mundial de LoL: o mesmo vale para os logos dos times, que são marcas dos times, não da Riot. Continua proibido
   qualquer logo da Riot Games (política "Legal Jibber Jabber").

## Consequências

- Risco jurídico aceito pelo dono: direito autoral sobre a arte dos escudos e uso de marca. Mitigação: uso só para
  identificar, sem alteração, gratuito, com retirada imediata a pedido. Isto não é parecer jurídico.
- Cobertura em 2026-11-04: Série A 20 de 20; Série B 20 de 20; Premier League 20 de 20; LaLiga 20 de 20; Champions
  36 de 36; Mundial de LoL 14 de 16 (LØS pelo artigo da Wikipédia em português; LYON e Team Secret Whales seguem
  com a sigla). A Leaguepedia (Fandom) não é usada: os termos proíbem acesso automatizado sem permissão escrita.
- Revoga a parte da D-028 que tirava os três escudos da Série A; o marcador (D-029) fica para quem não tem escudo.

## Adendo (2026-11-04): logos de LYON e Team Secret Whales pelo egamersworld

- Nenhuma Wikipédia tem o logo dos dois times. O dono do produto apontou a página do LYON no egamersworld
  ("pegue daqui", "e pegue da tsw tbm").
- A seção 4 dos termos do egamersworld diz que as imagens do portal não podem ser reutilizadas e exige atribuição.
  O dono do produto aceitou também esse risco ("Usar o egamersworld").
- O cadastro (`crest_sources.csv`) registra a URL da imagem, a página do time e a atribuição
  ("Logo: egamersworld.com"). O rodapé do Mundial de LoL dá o crédito.
- O logo do Team Secret Whales é branco: o manifesto marca `dark` e o site o mostra sobre um quadrado em tinta, sem
  alterar a imagem.
- Cobertura do Mundial de LoL: 16 de 16. No total, 170 de 170 times têm escudo.
- Se o egamersworld pedir a retirada, os dois voltam ao marcador com a sigla.

