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
