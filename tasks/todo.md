# Tasks

## Altium to SPICE Exporter
- [x] Analiza formatu pliku `.NET` (Altium Netlist)
- [x] Analiza BOM `.xls`
- [x] Utworzenie modelu danych `altium_model.py`
- [x] Implementacja parsera `altium_parser.py`
  - [x] Parser sekcji komponentÃ³w `[...]`
  - [x] Parser sekcji sieci `(...)`
  - [x] Parser wartoÅci z pola comment (100k, 10p, 1k5, 0R, etc.)
  - [x] Parsowanie BOM z xlrd
  - [x] Konwersja do `Circuit`
  - [x] Eksport do tekstu SPICE
- [x] Integracja z CLI (`altium-to-spice` command)
- [x] Testy jednostkowe `test_altium_parser.py`
- [x] Weryfikacja na rzeczywistym pliku 058-SBS-07 Comparator
- [x] Aktualizacja `tasks/lessons.md`

## AI Circuit Analysis
- [x] Wczytanie wyizolowanego obwodu Comparator_A_1.cir
- [x] Analiza topologii (dzielniki napiêæ, filtry RC)
- [x] Wnioski na temat uk³adu kondycjonowania sygna³u
