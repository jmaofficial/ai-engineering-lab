Chattgränssnitt
==============

Starta tjänsten med `.venv/bin/uvicorn app.main:app --reload` och öppna
[http://127.0.0.1:8000/](http://127.0.0.1:8000/). Ingen separat frontend-server
eller installation av JavaScript-paket behövs. Vyn använder samma `/agent`-API
och stödjer Markdown-tabeller, kodblock, ny chatt och pågående-anrop-indikering.
Enter skickar, Shift+Enter ger en ny rad. Den aktuella konversationen sparas i
webbläsarens localStorage (de senaste 200 meddelandena). New chat återställer
vyn; tidigare konversationer finns fortfarande i PostgreSQL. Sidan återställer
utkastet vid fel och skickar inte om anrop automatiskt.

Agentens minneshämtning
======================

Agenten kan använda `search_memories(query)` när uppgiften kräver mer kontext.
Sökningen matchar ord i aktiva minnen, sorterar efter importance och sedan ID.
Tom sökfråga bläddrar bland alla aktiva minnen. Upprepade anrop hämtar nya
resultat inom samma användartur. Detta är ordmatchning, inte semantisk sökning.
Om en ny sökfråga saknar ordträffar returneras i stället en tydligt märkt sida
med andra sparade minnen (`retrieval_mode=browse_fallback`). Det hjälper vid
olika ordval utan domänspecifika synonymer. Dessa resultat är inte påstått
semantiskt relevanta och följer samma sid- och budgetgränser. Upprepade anrop
med samma fråga fortsätter bland dessa minnen utan dubbletter.

Följande miljövariabler kan anges i `.env` (starta om tjänsten efter ändring):

| Inställning | Standard | Betydelse |
| --- | --- | --- |
| `MEMORY_PAGE_SIZE` | 5 | Max antal minnen per anrop |
| `MEMORY_MAX_ITEMS` | 20 | Max antal hämtade minnen per användartur |
| `MEMORY_MAX_CHARS` | 12000 | Max tecken i hämtad minnestext per användartur |
| `AGENT_MAX_ITERATIONS` | 16 | Max modellanrop per användartur, inklusive slutsvar |

Verktyget skiljer på `query_exhausted`, `more_available` och
`budget_exhausted`. Modellen bedömer själv om den behöver söka vidare eller
fråga användaren. Sista modellsteget körs utan tools så att agenten kan svara
eller fråga även när anropsbudgeten är slut. Modellens bedömning är inte en
garanti för att all relevant information har hittats.

Teckengränsen gäller bara hämtad minnestext. Full tokenbudget för historik,
systeminstruktioner, toolresultat och svar återstår att implementera.
Historiken behåller fortfarande de senaste tio meddelandena, oavsett längd.
Minneskonsolideringens prompt har ännu ingen tokenbudget heller.

Lokala tester: `.venv/bin/python -m unittest discover -s tests -v`

Riot-integration
================

Lägg `RIOT_API_KEY=din_nyckel` i den ignorerade `.env`-filen och starta om
tjänsten. Klistra inte in nyckeln i chatten. En development key hämtas från
[Riot Developer Portal](https://developer.riotgames.com/) och behöver förnyas
efter 24 timmar enligt [Riots dokumentation](https://developer.riotgames.com/docs/portal).

Agenten har tre tools: `riot_account`, `riot_match_history` och
`riot_analyze_champions`. Exempel: ”Analysera min championpool för ranked solo.
Mitt Riot ID är Namn#EUW och regionen är europe. Jag spelar top.”
För EUW/EUNE används regional routing `europe`; verktygen accepterar även
`americas`, `asia` och `sea`.

| Miljövariabel | Standard | Betydelse |
| --- | --- | --- |
| `RIOT_MAX_MATCHES` | 20 | Max matcher per verktygsanrop, högst 100 |
| `RIOT_REQUEST_BUDGET` | 120 | Max HTTP-anrop under en användartur |
| `RIOT_TIMEOUT_SECONDS` | 10 | Timeout per HTTP-anrop |

Analysen hämtar som standard 10 matcher och kan bläddra med `start`. Solo/duo
(420) och flex (440) analyseras separat. Resultatet innehåller statistik per
champion och roll samt kompakta matchrader; råa matchobjekt skickas inte till LLM.
CS/min inkluderar lane- och jungle-CS. Remakes filtreras med
`gameEndedInEarlySurrender`. Resultatet visar patchar, antal matcher och eventuella
avbrott. Win rate är observerad andel vinster, inte en uppskattad kausal effekt
av ditt championval. Saknad roll märks UNKNOWN.

Anrop cachas inom användarturen. Vid HTTP 429 respekteras Retry-After genom att
stoppa nya anrop i samma serverprocess; ingen blockerande retry-loop körs.
Flera serverprocesser delar ännu inte rate-limit-status eller cache. För större
datainsamling behövs gemensam rate limiter och persistent matchcache.

Den här versionen analyserar personlig historik. Global meta, aktuell champion
select och fri körning av Python/Bash ingår inte. Ett levande integrationstest
kräver konfigurerad nyckel och ett Riot ID.

Agentstyrd statistisk analys
===========================

Bygg analysmiljön med `docker build -t lol-analysis:local analysis` och starta om
API-tjänsten. Docker måste vara tillgängligt för tjänstens process.
`collect_match_dataset` hämtar råa matchobjekt i sidor till `.analysis/matches.sqlite`.
Agenten väljer sidstorlek, antal sidor och kö (0=alla, 420=solo, 440=flex).
Ingen roll-, patch- eller remakefiltrering görs vid insamling. Match-ID dedupliceras.
`next_start` kan användas efter avbrott; tom sida bekräftar slut på historiken.
Offseten kan förskjutas om nya matcher spelas under insamlingen.

`inspect_match_dataset` visar roll- och patchfördelning, remakeflaggor, kolumner,
tidsintervall, hämtade historikintervall och kvarvarande Riot-budget. Fortsättning
beräknas från sammanhängande hämtade sidor; äldre dataset utan sidmetadata kan
behöva bläddras om, men matchobjekten återanvänds. Agenten väljer själv om äldre
data är användbar och motiverar när den slutar samla.

`analyze_match_dataset(dataset_id, code, rationale)` kör agentens Pythonkod med
`df` (spelarens rader), `matches` (råa matchobjekt), pandas, NumPy, SciPy och
statsmodels. `df` innehåller deltagarfälten, patch, kö, tidpunkt, matchlängd och
motståndarens champion för samma roll när den kan hittas. Agenten väljer filter,
tester och mängd data efter frågan och osäkerheten. Kod, motivering och output
sparas under `.analysis/runs/`. Instruktionerna kräver analysplan och att skilja
explorativa resultat från bekräftande tester; detta är modellinstruktioner,
inte en automatisk garanti mot statistiska metodfel.

Felaktiga verktygsargument och körningsfel returneras till modellen så att den
kan korrigera dem. Varje Pythonresultat anger om körningen lyckades; avklippt
output eller timeout räknas inte som en slutförd analys. Verktygsanrop och slutliga
svar sparas i `.analysis/agent_runs/` för granskning. Dessa lokala loggar innehåller
kontodata och kod, men ingen Riot-nyckel. Modellleverantörsfel ger HTTP 503 och
oanvändbara modellsvar HTTP 502, i stället för ett ospecificerat serverfel.

`collect_more_matches(dataset_id, count)` fortsätter med sparat konto och cursor;
modellen behöver inte kopiera långa spelar-ID:n mellan sidor. API-fel betyder
aldrig att historiken är slut. Analyskörningen returnerar automatiskt radantal,
roller, remakeflaggor och patchfördelning före och efter DataFrame-filtrering.
Slutsvaret granskas mot dessa metadata, Pythonkoden och utskrifterna. Vid
underkänd granskning får agenten rätta analysen inom samma anropsbudget.
Även granskningsanrop räknas mot `AGENT_MAX_ITERATIONS`.

Både agent och granskare använder samma tidigare modell,
`gemini-3.5-flash-lite`. Ingen annan modell aktiveras för granskning. Agenten
följer användarens önskade språk, annars språket i användarens senaste fråga;
intern granskningsfeedback ska inte ändra språkvalet. LLM-granskning minskar
risken för fel men garanterar inte att statistiska slutsatser är korrekta.

Containerprov med syntetisk data:
`RUN_CONTAINER_TESTS=1 .venv/bin/python -m unittest discover -s tests -v`

Verkligt integrationstest (kräver startat API och gör Gemini/Riot-anrop):
`.venv/bin/python experiments/test_statistical_agent.py --riot-id 'Namn#Tag' --region europe`
Använd `--prompt` för en egen fråga eller ett uttryckligt språkönskemål.

Containern saknar nätverk och hemligheter, har skrivskyddat filsystem och dataset,
512 MB RAM, en CPU, processgräns och begränsad temporär lagring. Ingen kod körs
direkt på värden som reservlösning. Gränser som kan ändras i `.env`:

| Inställning | Standard | Betydelse |
| --- | --- | --- |
| `ANALYSIS_MAX_MATCHES` | 1000 | Max lagrade matcher per dataset |
| `ANALYSIS_TIMEOUT_SECONDS` | 30 | Körningstid per analys |
| `ANALYSIS_OUTPUT_CHARS` | 12000 | Outputgräns (verkställs som bytes) |
| `ANALYSIS_DATA_DIR` | `.analysis` | Lokal dataset- och analyslagring |

Riot- och agentbudgetarna ovan gäller fortfarande. Resursgränser betyder inte
att statistiskt tillräckligt underlag finns. Flera analyser får göras per tur
inom agentens anropsbudget. Kontodata lagras lokalt för denna privata app;
åtkomstkontroll per användare behövs innan tjänsten delas med andra.
Matplotlib finns i containern, men figurfiler exporteras ännu inte till chatten.
Full tokenbudget, matchtimeline-hämtning och fri Bash är separata framtida steg.

Agentbeteende
=============

De generella instruktionerna finns i `app/agents/instructions.py`. Agenten väljer
själv om och vilka verktyg som behövs; ingen LoL- eller statistikarbetsgång krävs
av systemprompten. Domänspecifika funktioner och metodstöd beskrivs i respektive
verktyg. Ett motiverat beslut under osäkerhet skiljs från ett statistiskt bevis.
Granskaren bedömer om svaret besvarar användarens fråga och stämmer med tillgänglig
evidens, utan att kräva vissa verktyg eller ett fast svarsformat.

Integrationstestet kräver inte en viss verktygsföljd. Lägg till `--require-python`
när du uttryckligen vill testa att agenten kör Python; lämna bort flaggan när
du testar fritt verktygsval eller ett direkt svar.
