import codecs

path = 'c:/Users/micha/Desktop/SolverSCH/tasks/lessons.md'
with codecs.open(path, 'a', encoding='utf-8') as f:
    f.write('\n\n## 5. Unikaj Catastrophic Backtracking w Wyrazeniach Regularnych dla SVG\n')
    f.write('**Wzorzec bledu:** Uzywanie `.*?</g>` z flaga `re.DOTALL` w pythonie przy parsowaniu plikow SVG z netlistsvg (ELK) doprowadza do wykladniczego czasu wykonania RegExp i zawieszenia narzedzia Exporter.\n')
    f.write('**Rozwiazanie:** Przy wyciaganiu koordynatow unikaj wylapywania calej zawartosci grupy. Parsuj wylacznie tagi otwierajace, np. `re.finditer(r\'<g([^>]+id="([^"]+)"[^>]*)>\', content)`. Dzieki temu parser wykonuje sie bledyskawicznie w czasie O(N).\n')
    
    f.write('\n## 6. ELK Partitioning Infinite Loop Crash\n')
    f.write('**Wzorzec bledu:** Nadpisywanie wektorow wejscia s:position (np. s:position="right" dla kolektora NPN) wewnatrz netlistsvg w polaczeniu z narzucaniem limitow partycjonowania silnika (org.eclipse.elk.partitioning) powoduje infinite loop wewnatrz procesu node.js.\n')
    f.write('**Rozwiazanie:** Komponenty SVG skoryguj zostawiajac oryginalne `s:position="top"` dla ELKa, a przesuniecia lub grupowania blokow (np. sily ciagnace zasilanie zawsze na lewo) implementuj post-factum (np. przesuniecie bezwzgledne w osi X po zakonczeniu dzialania ELKa).\n')
