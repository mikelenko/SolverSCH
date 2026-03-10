# Hierarchical RAG dla Dużych Datasheetów

- [x] `datasheets/build_index.py` — offline indexer: section detection (font-size), smart chunking (≤2000→1 chunk, >2000→split+overlap), table extraction (markdown), Component Card via Gemini, zapis `.index.json` + `.card.json`
- [x] `tool_query_datasheet` — priority 1: ładuj `.index.json` (skip PDF), priority 2: live PDF parse. Wyniki zawierają `section` metadata. Dołącza `component_card` z `.card.json` gdy dostępna.
- [x] `_load_component_cards()` — skanuje `datasheets/*.card.json`, matchuje z BOM (pomija pasywne)
- [x] `_format_prompt()` — nowa sekcja `### COMPONENT DATASHEETS` wstrzykiwana do każdego promptu
- [x] `tests/test_hierarchical_rag.py` — 6 testów (build_index, index-first loading, section metadata, fallback PDF, card injection, no-card fallback)
- [x] 64/64 testów zielonych

---

# Integracja Simulator → AI Design Review Pipeline

- [x] `Simulator.review()` + `_build_bom()` — lazy import DesignReviewAgent, kompiluje BOM + sim_results, wywołuje agent
- [x] `Simulator._build_bom()` — iteruje po komponentach, wyciąga ref/type/value/nodes
- [x] CLI `solversch review <netlist> [--intent ...] [--model ...]` — parsuje netlistę, uruchamia dc(), wywołuje review()
- [x] `tests/test_review_pipeline.py` — 4 testy (payload structure, markdown return, missing API key, partial results)
- [x] 58/58 testów zielonych

---

# Zadanie: Uruchomienie testu Gemini 3.1 Flash Multimodal Flow

## Plan
- [x] Utworzenie pliku `tests/test_gemini_multimodal.py` z przekazanym kodem.
- [x] Sprawdzenie istnienia `GEMINI_API_KEY` w `.env` (KLUCZ DODANY).
- [x] Sprawdzenie istnienia obrazka `import/LM358_pinout.png` (Obrazek istnieje).
- [x] Instalacja wymaganych bibliotek: `google-generativeai python-dotenv pytest-asyncio` (ZAKOŃCZONO).
- [x] Uruchomienie skryptu: `python tests/test_gemini_multimodal.py`.
- [x] Weryfikacja wyniku działania testu (SUKCES).
