# Lessons Learned (Wzorce błędów i rozwiązania)

## 1. Wybuch Równania Shockleya (Overflow / NaN)
**Wzorzec błędu:**
Przy implementacji modelu diody w pętli Newtona-Raphsona, jeśli Solver "zgadnie" zbyt duże napięcie wejściowe (np. $5V$), człon wykładniczy $exp(V_d / (n \cdot V_t))$ wykracza poza zakres zmiennoprzecinkowy (np. $exp(192)$). Wynikiem jest ogromny prąd ($I_d$) i konduktancja ($G_{eq}$), co prowadzi do błędów `math range error`, wyrzucania `NaN` i macierzy osobliwych uniemożliwiających rozwiązanie.

**Rozwiązanie (Zasada żelazna):**
W metodzie `stamp_nonlinear`, ZASTRZEGAMY limitowanie spadku napięcia widzialnego na diodzie (Voltage Limiting / Damping). Nie ufać ślepo wynikom z poprzedniej iteracji `x_prev`. Napięcie musi zostać "obcięte" na sensownym fizycznym limicie (np. maksymalnie $0.8V$ w obliczeniach), dzięki czemu Newton-Raphson pokonuje drogę mniejszymi, łagodniejszymi stabilnymi krokami unikając wybuchów. Wzór do wdrożenia to np. `Vd_safe = min(Vd, 0.8)`.

## 2. Test Driven Development (TDD) i Regresja
**Wzorzec błędu:**
Dokonywanie tak zwanych "drobnych, niegroźnych zmian", które uderzają w silnik fizyczny `SolverSCH` lub przyległą logikę komponentów bez twardego pokrycia asercją. Ryzyko wygenerowania "efektu motyla" psującego stare środowisko projektanta.

**Rozwiązanie (Zasada żelazna):**
Bezwzględny wymóg uruchamiania zautomatyzowanych skanów (`python -m pytest tests/`) po JEDNEJ wdrożonej fukcjonalności - zasada "uruchamiaj testy wszystkiego co już zrobiłeś". Na nową architekturę musi wejść odpowiadający blok pod `tests/test_x.py`. Weryfikacja musi rzucać 100% PASS przed ogłoszeniem końca przebiegu i zadeklarowaniem gotowości. Nigdy nie polegaj wyłącznie na jednorazowym runie w głównym wywołaniu pliku.

## 3. PyVis Schematic i hermetyzacja (Encapsulation)
**Wzorzec błędu:**
Poleganie na powszechnym nazewnictwie atrybutów bez weryfikacji w kodzie źródłowym (np. próba użycia `circuit.components` ukrytego pod metodą `get_components()`).

**Rozwiązanie (Zasada żelazna):**
Zawsze weryfikuj interfejs pliku poprzez `view_file` PRZED użyciem go w nowym systemie. SolverSCH implementuje strict-access, więc iteracja przebiega przez gettery: `circuit.get_components()` oraz `comp.nodes()`.

## 4. Odlączone Węzły przy Dynamicznych Źródłach (Floating Nodes) i Zwarcia (Shorting)
**Wzorzec błędu:**
1. Definiowanie pomocniczego napięcia DC w netliście z węzłem testowym (np. "dummy"), a nie faktycznym punktem w układzie (np. "in") skutkuje brakiem jakiejkolwiek wymuszonej dynamiki płaskim przebiegiem w wynikach (flatline).
2. Wpinanie idealnego źródła napięcia (np. `V_set b1 0 0.0`) PROSTO w węzeł w układzie ze sprzężeniem zwrotnym (np. bazę tranzystora w przerzutniku SRAM). Idealne źródło ma impedancję wyjściową $0 \Omega$, więc zwiera węzeł `b1` do masy w czasie gdy impuls wynosi 0V, rozrywając logikę pozytywnego sprzężenia zwrotnego i generując np. ujemne skoki matematyczne z pętli Newtona-Raphsona.

**Rozwiązanie (Zasada żelazna):**
- **Sygnał bezpośredni (np. inwerter):** `V_dummy in 0 0.0` wywoła na wejściu inwertera zaplanowany sygnał. Napięcie $0V$ jest stanem wyłączonym i idealnie symuluje zasilanie bez naruszania struktury.
- **Sprzężenie zwrotne (np. SRAM Flip-Flop):** Używaj rezystora izolującego (trigger resistor). Zastosowanie `V_set vset 0 0.0` oraz `R_set vset b1 10k` gwarantuje, że stymulant w stanie 0V symuluje podłączenie logiczne przez pull-down, umożliwiając węzłom sprzężenia z kolektora (np. `c2`) "podciągnięcie" stanu `b1` powyżej progu otwarcia tranzystora bez oporu $0 \Omega$ do uziemienia.

## 5. Macierze Osobliwe (Singular Matrix) dla Odciętych Tranzystorów
**Wzorzec błędu:**
Podczas rozwiązywania obwodów nieliniowych (takich jak bramka CMOS), gdy system NR (Newton-Raphson) znajduje się w punkcie początkowym (np. wektor zgadnięcia $x^{(0)}$ jest złożony z samych zer), tranzystory sterujące określonym węzłem mogą wejść w absolutny stan "Cutoff" (odcięcie). Jeśli $g_{ds} = 0.0$ oraz $g_m = 0.0$, węzeł staje się całkowicie odcięty w ujęciu matematycznym. Rząd w macierzy Jakobianu (A_csr) ma wyłącznie wartości $0.0$, co tworzy "Singular Matrix" (macierz osobliwą) i powoduje wyrzucenie błędów `NaN != 5.0` w testach jednostkowych.

**Rozwiązanie (Zasada żelazna):**
W metodzie ładującej modele nieliniowe do macierzy (`stamp_nonlinear`), nałóż żelazną ochronę za pomocą wirtualnych konduktancji pasożytniczych minimum ($G_{min} = 10^{-12} S$). Dla tranzystora MOSFET $G_{min}$ musi występować na diagonalach (odpowiadających samoprzewodnictwu węzła) ORAZ w relacji krzyżowej Drain-Source (D-S) i Gate-Source (G-S). Zabezpieczenie ścieżki D-S prądem upływu $1 pS$ zapobiega tworzeniu wiszących matematycznie węzłów ułatwiając zbiegnięcie całego układu, co ratuje macierz przed wyrzuceniem `ValueError` podczas operacji odwracania/znajdywania wyznacznika.

## 2026-03-04 Wymuszanie składni SPICE dla LLM (Żelazne Zasady)
- **Problem:** Modele LLM mają tendencję do generowania skomplikowanego, pełnego słów kluczowych kodu SPICE (np. V1 in 0 DC 5V, definiowanie wzmacniaczy operacyjnych poprzez bloki powiązane dyrektywami .SUBCKT), z którym nie radzi sobie nasz prosty parser i sprzężony z nim solvery MNA. LLM-y również gubią potrzebę stosowania źródeł zasilania wejść przy projektowaniu pasywnych filtrów.
- **Rozwiązanie (Zasada żelazna):** W kodzie z przepływem auto-designera musi zostać zachowany sztywny system prompt / instrukcje uziemiające (żelazne_zasady), narzucające modelom precyzyjne stosowanie dialektu akceptowanego przez solver (czyste wartości 5 zamiast 5V, poprawne definiowanie tranzystorów i użycie zintegrowanego modelu U1 out in+ in- zamiast pod-obwodów). Musimy również zmuszać model do aplikowania sztywnych punktów pomiarowych in i out.


## 3. Przechodzenie na ustandaryzowany Python Logging z Print()
**Wzorzec błędu:** Zostawianie luźnych print() w klasach środowiska (np. AutoDesigner) powoduje chaos. 
**Rozwiązanie:** Czyste logowanie przez logging.getLogger, a wejście/wyjście terminala oddzielone interfejsem CLI.

## 4. Ochrona Zależności Projektu
**Wzorzec błędu:** Instalowanie pip locally czasami lockuje executables (uruchomiony python w tle z poprzednich sesji). 
**Rozwiązanie:** Konfiguracja pyproject.toml [project.scripts] uodparnia nas na zarządzanie skryptami z zewnątrz.

## 5. Unikaj Catastrophic Backtracking w Wyrazeniach Regularnych dla SVG
**Wzorzec bledu:** Uzywanie `.*?</g>` z flaga `re.DOTALL` w pythonie przy parsowaniu plikow SVG z netlistsvg (ELK) doprowadza do wykladniczego czasu wykonania RegExp i zawieszenia narzedzia Exporter.
**Rozwiazanie:** Przy wyciaganiu koordynatow unikaj wylapywania calej zawartosci grupy. Parsuj wylacznie tagi otwierajace, np. `re.finditer(r'<g([^>]+id="([^"]+)"[^>]*)>', content)`. Dzieki temu parser wykonuje sie bledyskawicznie w czasie O(N).

## 2026-03-09 Przestrzeganie CLAUDE.md — Luki w Workflow

**Problem:** Podczas dużej sesji refaktoryzacji (Faza 0–5) plan trafił do `.claude/plans/` zamiast do `tasks/todo.md`. Plik `tasks/lessons.md` nie był aktualizowany na bieżąco po sesjach. CLAUDE.md był stosowany częściowo — plan mode, subagenty, testy po każdej fazie — ale ślad pisemny w `tasks/` był zaniedbany.

**Rozwiązanie (Zasada żelazna):**
- Po zakończeniu każdego większego zadania zawsze dopisz wpis do `tasks/todo.md` (co zrobiono) i `tasks/lessons.md` (co się nauczono).
- Plan tryb (`EnterPlanMode`) → zapis planu w `.claude/plans/` jest OK dla struktury Claude, ale TAKŻE należy dodać checklistę do `tasks/todo.md` zanim zacznie się implementacja.
- Przy starcie sesji: przeczytaj `tasks/lessons.md` zanim zaczniesz cokolwiek nowego.

## 6. ELK Partitioning Infinite Loop Crash
**Wzorzec bledu:** Nadpisywanie wektorow wejscia s:position (np. s:position="right" dla kolektora NPN) wewnatrz netlistsvg w polaczeniu z narzucaniem limitow partycjonowania silnika (org.eclipse.elk.partitioning) powoduje infinite loop wewnatrz procesu node.js.
**Rozwiazanie:** Komponenty SVG skoryguj zostawiajac oryginalne `s:position="top"` dla ELKa, a przesuniecia lub grupowania blokow (np. sily ciagnace zasilanie zawsze na lewo) implementuj post-factum (np. przesuniecie bezwzgledne w osi X po zakonczeniu dzialania ELKa).

## 7. LLM Tool-Calling Loop Degeneracy (Agentic Discovery)
**Wzorzec bledu:** Lokalne modele LLM (np. Qwen 14B) w petli discovery wielokrotnie wywoluja to samo narzedzie z identycznymi parametrami, nie mowiac "READY". Bez deduplication petla wyczerpuje max_iterations produkujac bezuzyteczne wyniki. Dodatkowo, jesli odpowiedz "READY" modelu NIE zostanie dodana do historii wiadomosci, Phase 2 (raportowanie) dziedziczy kontekst z "musisz odpowiedziec READY" i sam zwraca "READY" zamiast raportu.

**Rozwiazanie (Zasada zelazna):**
- Sledzenie wywolanych narzedzi w `set((func_name, args_json))`. Duplikaty -> nie wykonuj, wstaw wiadomosc "juz wywolales to narzedzie, uzyj wynikow lub powiedz READY".
- Jesli WSZYSTKIE wywolania w turze sa duplikatami -> wymus "READY" bez dodawania wiadomosci asystenta z tool_calls (unikaj malformed conversation bez tool response).
- Kiedy model odpowie "READY", DODAJ ta odpowiedz do `messages` ZANIM przejdziesz do Phase 2. Inaczej Phase 2 nie widzi zakonczenia discovery i produkuje smieci.
- Phase 2 reporting directive musi EXPLICITE zabronic JSON/code blocks i wymieniac wymagane sekcje.

## 8. BM25Okapi vs BM25Plus — mały korpus daje wyniki zero/ujemne
**Wzorzec bledu:** `rank_bm25.BM25Okapi` uzywa IDF = log((N-df+0.5)/(df+0.5)) BEZ korekty +1. Przy N=2, df=1 → IDF=log(1)=0. Przy N=1, df=1 → IDF<0. Skutek: scores zawsze 0, wyniki puste, testy padaja na pustej liscie.
**Rozwiazanie (Zasada zelazna):** Uzywaj `BM25Plus` zamiast `BM25Okapi`. BM25Plus dodaje delta (domyslnie 1.0) do tf komponentu, gwarantujac zawsze niezerowe wyniki dla pasujacych tokenow niezaleznie od rozmiaru korpusu.

## 10. type: ignore[arg-type] dla asyncio.to_thread z nested functions
**Wzorzec bledu:** Checker (pyright/pylance) nie moze zinferować typu nested function (`() -> None`, `() -> str`) gdy zwracany typ zalezy od external package bez stubs (np. google-genai). Rzuca `bad-argument-type` na `asyncio.to_thread(func)` nawet gdy kod jest poprawny.
**Rozwiazanie (Zasada zelazna):** Dodaj `# type: ignore[arg-type]` na linii z `asyncio.to_thread(...)`. Uzyj wzorca z `Dict` jako holder dla wyniku (`raw_response: Dict[str, Any] = {}`), zeby obejsc problem z inferowaniem unii typow zwrotnych.

## 9. Cache-first przed file-lookup w narzedziu RAG
**Wzorzec bledu:** Sprawdzanie istnienia pliku PRZED sprawdzeniem cache powoduje ze testy pre-populujace cache dostaja blad "file not found" mimo ze dane sa w pamieci.
**Rozwiazanie (Zasada zelazna):** Zawsze sprawdz `if comp_key not in cache` jako pierwszy warunek. Jesli cache hit — przeskocz caly I/O. File lookup nastepuje TYLKO gdy cache miss.

## 11. Numpy / complex128 JSON serialization w pipeline AI
**Wzorzec bledu:** Przekazywanie wynikow AC analysis (zawierajacych `numpy.complex128`, `numpy.float64`) do `json.dumps()` w `_format_prompt` powoduje `TypeError: Object of type complex128 is not JSON serializable`. Problem ujawnia sie dopiero przy integracji Simulator.review() z AC sweep — testy DC nie wykrywaja tego bledu.
**Rozwiazanie (Zasada zelazna):** Uzywaj dedykowanego `_safe_json()` z handlerem `default=` obslugujacym `np.integer`, `np.floating`, `np.complexfloating` i `np.ndarray`. Nigdy nie przekazuj surowych wynikow z numpy do `json.dumps()` bez serializera.

## 12. Section Detection w PDF — false positive headings
**Wzorzec bledu:** `MIN_HEADING_FONT_RATIO = 1.15` przy body font 8.8pt traktuje zbyt wiele linii jako naglowki (feature bullets o 11pt, podpisy tabel, etykiety rysunkow jak "68111 TA01a"). Wynik: 394 "sekcji" zamiast ~26 prawdziwych rozdzialow datasheeta LTC6811.
**Rozwiazanie (Zasada zelazna):** 
- Podniesc `MIN_HEADING_FONT_RATIO` do 1.35
- Dodac `_is_valid_heading()` z: min 2 slowa, filtr bullet pointow (n/•/–), filtr etykiet rysunkow (>50% cyfr), wymaganie min 1 slowa alpha >=3 znaki
- Dodac `MIN_SECTION_CHARS = 50` — odrzucaj sekcje krotsze niz 50 znakow
- Rezultat: 394 → 26 unikalnych sekcji, 740 → 427 chunkow (42% mniej danych).

\ n # #   1 3 .   L T s p i c e   F l o a t i n g   N o d e s   i n   I d e a l   O p A m p   M a c r o m o d e l s \ n * * W z o r z e c   b l e d u : * *   L T s p i c e   ( w   w y e k s p o r t o w a n y c h   n e t l i s t a c h )   w y r z u c a   f a t a l   e r r o r   ' s i n g u l a r   m a t r i x '   l u b   p o   p r o s t u   z w r a c a   e x i t   c o d e   1 ,   j e s l i   p i n y   z a s i l a j a c e   ( V C C ,   V S S )   w   . S U B C K T   s a   t y l k o   w z m i a n k o w a n e   w   p o r c i e ,   a l e   n i g d z i e   n i e   p o d l a c z o n e   w   c i e l e   ( n p .   i d e a l n e   E 1   O U T   0   I N _ P   I N _ N   1 0 0 0 0 0 ) .   N a r z e d z i e   \ N e t l i s t P a r s e r \   s t a n d a r d o w o   n i e   k o p i o w a l o   t e z   d y r e k t y w   \ . M O D E L \ ,   c o   p o t e g o w a l o   c r a s h e   L T s p i c e   p r z y   n i e r o z p o z n a n y c h   d i o d a c h   Z e n e r a . \ n * * R o z w i a z a n i e   ( Z a s a d a   z e l a z n a ) : * *   Z a w s z e   d o d a w a j   r e z y s t o r y   ' d u m m y '   ( n p .   1 G   o h m   d o   m a s y )   n a   p i n a c h   z a s i l a j a c y c h   ( V _ P O S ,   V _ N E G )   w e w n a t r z   i d e a l n y c h   \ . S U B C K T \ ,   z e b y   L T s p i c e   w i d z i a l   p o p r a w n a   m a c i e r z   k o n d u k t a n c j i .   P a r s e r   ( \ N e t l i s t P a r s e r \ )   m u s i   z a w s z e   k o p i o w a c   l i n i e   z   \ . M O D E L \   d o   o b i e k t u   o b w o d u   ( j a k o   \ M o d e l C a r d \ ) ,   z e b y   L T s p i c e E x p o r t e r   f i z y c z n i e   u m i e s z c z a l   d e f i n i c j e   m o d e l i   p o l p r z e w o d n i k o w   w   p l i k u   \ . c i r \   d o   s y m u l a c j i .  
 