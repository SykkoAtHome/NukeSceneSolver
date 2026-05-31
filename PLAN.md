# Nuke Scene Solver - Plan działania

## Zasady realizacji

- Projekt jest samodzielnym narzędziem dla Nuke 15.1.
- Solver powstaje od zera na podstawie geometrii projekcyjnej i publikacji Guillou et al.
- `core` nie może zależeć od `nuke`, Qt ani repo fSpy.
- Najpierw poprawność matematyczna i testy, potem UI.
- Każdy etap powinien kończyć się działającym, możliwym do zweryfikowania wynikiem.

## Docelowa struktura repo

```text
nuke_SceneSolver/
  README.md
  PRD.md
  PLAN.md
  init.py
  menu.py
  scene_solver/
    __init__.py
    core/
      __init__.py
      geometry.py
      coordinates.py
      models.py
      solver_2vp.py
    nuke_integration/
      __init__.py
      camera_adapter.py
      panel_registration.py
    ui/
      __init__.py
      panel.py
      canvas.py
  tests/
    test_geometry.py
    test_coordinates.py
    test_solver_2vp.py
  nuke_tests/
    test_camera2_projection.py
```

## Stan realizacji

- Etapy `0-2`: zakończone.
- Etapy `3-4`: zakończone.
- Etap `5`: zakończony dla centralnego principal point wymaganego przez MVP.
- Etap `6`: zakończony. Narzędzie operuje jako dockowalny panel PySide2 z interaktywną kanwą, obsługą zoomu/panningu, etykietami osi, siatką podłogi oraz kontrolkami HUD (Fit, 1:1, Grid, Reset).
- Etap `7`: zakończony. Dodano tryb dopasowania przez manipulację widocznymi krawędziami prostopadłościanu 3D na kanwie panelu (Box Match mode) z wyliczaniem linii w oparciu o solve. Niezależny Scene Origin pozwala na pozycjonowanie świata poza Boxem.
- Etap `8`: zakończony. Dodano linię referencyjną, overlay horyzontu,
  skalowanie translacji kamery oraz akcje eksportu helperów sceny. Walidacja
  interaktywna w Nuke 15.1 objęła idealny cube oraz niesześcienny cuboid z inną
  kamerą.
- Następny krok: Etap `9` (Principal Point i Optyka).

---

## Etap 8 - Skala i Eksport Sceny (Reference Distance & Export)

Cel: Nadać scenie właściwą skalę oraz umożliwić szybki start pracy w środowisku 3D wewnątrz Nuke poprzez generowanie geometrii pomocniczej.

Zadania:

- **UI Canvas:**
  - dodać tryb wprowadzania "Linii Referencyjnej" (Reference Line) - odcinek o znanej długości,
  - dodać wizualizację Linii Horyzontu (Horizon Line) wyliczanej z punktów zbiegu,
  - dodać przełącznik HUD dla Horyzontu.
- **Solver Core:**
  - wyznaczyć punkty 3D odcinka przez przecięcie promieni z odpowiednią płaszczyzną,
  - przeskalować translację kamery na podstawie tego odcinka.
  - finalny workflow UI: skalować scenę na podstawie szacowanego wymiaru
    dopasowanego Box Match i niezależnego offsetu jego płaszczyzny podstawy.
- **Nuke Integration (Eksport Helperów):**
  - dodać przycisk `Create Scene Grid` (wygenerowanie node'a Grid podpiętego pod środek świata),
  - dodać przycisk `Create Origin Card` (wygenerowanie node'a Card w punkcie 0,0,0),
  - dodać przycisk `Create Match Box` (wygenerowanie geometrii Cube dopasowanej do Box Match).

Testy:
- odzyskanie długości odcinka syntetycznego,
- poprawność transformacji generowanych węzłów Nuke 3D.

## Etap 9 - Principal Point i Optyka

Cel: Rozszerzyć możliwości o precyzyjną konfigurację optyki (lens shift / offset).

Zadania:
1. Ręczna edycja Principal Point (przesuwanie środka optycznego).
2. Lens shift przez zmapowanie przesunięcia na knob `win_translate` kamery Nuke.
3. Wyliczanie Principal Point z trzeciego punktu zbiegu (3VP solver).
4. Tryb `1VP` (znana ogniskowa i linia horyzontu).

## Etap 10 - Trwałość ustawień i packaging

Cel: Przygotować narzędzie do codziennej pracy.

Zadania:
- zapisywać stan linii VP, Boxa i punktów w skrypcie Nuke (serializacja do knobs),
- automatyczne odtwarzanie stanu po ponownym otwarciu panelu,
- przygotowanie finalnej instrukcji instalacji i przykładowych skryptów.

---

## Definicja ukończenia produktu v1

Wersja `v1` jest gotowa, gdy użytkownik Nuke 15.1 może dopasować statyczną kamerę `Camera2` w trybie `2VP/Box`, ustawić horyzont, zdefiniować skalę, wyeksportować pomocniczą geometrię, zapisać stan w skrypcie Nuke i po ponownym otwarciu kontynuować pracę bez utraty ustawień.
