# Nuke Lens Solver - Plan działania

## Zasady realizacji

- Projekt jest samodzielnym narzędziem dla Nuke 15.1.
- Solver powstaje od zera na podstawie geometrii projekcyjnej i publikacji Guillou et al.
- `core` nie może zależeć od `nuke`, Qt ani repo fSpy.
- Najpierw poprawność matematyczna i testy, potem UI.
- Każdy etap powinien kończyć się działającym, możliwym do zweryfikowania wynikiem.

## Docelowa struktura repo

```text
nuke_LensSolver/
  README.md
  PRD.md
  PLAN.md
  init.py
  menu.py
  lens_solver/
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

Struktura może zostać skorygowana, jeśli pierwsze testy Nuke ujawnią prostsze rozwiązanie.

## Etap 0 - inicjalizacja repo

Cel: przygotować samodzielny szkielet projektu.

Zadania:

- utworzyć repo Git,
- dodać `README.md` z instrukcją instalacji developerskiej dla Nuke 15.1,
- utworzyć pakiet `lens_solver`,
- dodać podstawową konfigurację testów Python,
- ustalić minimalną wspieraną wersję Pythona zgodną z Nuke 15.1 na używanej instalacji,
- dodać `.gitignore` dla cache Pythona i lokalnych plików Nuke.

Warunek zakończenia:

- import `lens_solver` działa poza Nuke,
- pusty zestaw testów uruchamia się poprawnie.

## Etap 1 - fundament geometrii

Cel: zbudować niezależne i testowalne operacje matematyczne.

Zadania:

- dodać `Point2D`, `Vector3D`, `Segment2D`, `Matrix4`,
- zaimplementować przecięcie dwóch nieskończonych linii,
- dodać iloczyn skalarny, wektorowy, normalizację i długość,
- dodać operacje macierzy potrzebne do transformacji kamery,
- dodać kontrolowane tolerancje numeryczne,
- jawnie obsłużyć linie zerowej długości oraz prawie równoległe.

Testy:

- przecięcie linii prostych,
- linie równoległe,
- linie prawie równoległe,
- normalizacja wektora zerowego,
- poprawność iloczynu wektorowego,
- odwracanie i składanie macierzy używanych przez solver.

Warunek zakończenia:

- testy geometrii przechodzą poza Nuke.

## Etap 2 - układy współrzędnych obrazu

Cel: usunąć niejawne założenia dotyczące pikseli, aspect ratio i kierunku osi Y.

Zadania:

- zdefiniować układ względny UI: lewy górny róg `(0, 0)`, prawy dolny `(1, 1)`, oś Y w dół,
- zdefiniować znormalizowaną płaszczyznę obrazu solvera: środek obrazu `(0, 0)`, oś Y w górę,
- zaimplementować konwersje w obie strony,
- udokumentować zachowanie dla obrazu poziomego, pionowego i kwadratowego,
- dodać principal point jako jawny parametr.

Testy:

- round-trip każdej konwersji,
- narożniki oraz środek obrazu,
- formaty `1920x1080`, `1080x1920`, `2048x2048`.

Warunek zakończenia:

- każda konwersja ma test i dokumentowaną konwencję.

## Etap 3 - solver 2VP

Cel: wyliczyć intrinsics i orientację kamery z dwóch prostopadłych punktów zbiegu.

Zadania:

- obliczyć VP jako przecięcia par linii,
- przyjąć principal point na środku obrazu jako domyślne MVP,
- obliczyć względną ogniskową z geometrii VP,
- odrzucić konfiguracje prowadzące do `focal_length_squared <= 0`,
- obliczyć ortonormalną bazę rotacji kamery,
- obsłużyć mapowanie kierunków VP do wybranych osi świata,
- obliczyć trzeci kierunek przez iloczyn wektorowy,
- sprawdzić wyznacznik rotacji,
- obliczyć FOV poziomy i pionowy,
- zwrócić `SolveResult` z listami `warnings` i `errors`.

Testy:

- wygenerować syntetyczne kamery,
- rzutować osie świata do obrazu,
- tworzyć odcinki zbiegające się do otrzymanych VP,
- odzyskać ogniskową i rotację,
- porównać wynik z kamerą źródłową z tolerancją numeryczną,
- sprawdzić obrazy poziome i pionowe,
- sprawdzić konfiguracje niepoprawne.

Warunek zakończenia:

- solver odzyskuje parametry syntetycznych kamer bez zależności od Nuke.

## Etap 4 - origin i domyślna translacja

Cel: umieścić kamerę w przestrzeni przy zachowaniu dopasowanej perspektywy.

Zadania:

- potraktować wskazany punkt obrazu jako rzut origin świata,
- wyznaczyć promień kamery przechodzący przez origin,
- umieścić kamerę na domyślnej odległości od origin,
- jasno udokumentować, że bez odcinka referencyjnego skala sceny jest umowna,
- dodać test, że origin po projekcji wraca do zadanego piksela.

Warunek zakończenia:

- syntetyczny origin pokrywa się po ponownej projekcji.

## Etap 5 - adapter Camera2 dla Nuke 15.1

Cel: utworzyć standardową kamerę Nuke na podstawie `SolveResult`.

Zadania:

- uruchomić eksperymenty w Nuke 15.1 i udokumentować konwencje `Camera2`,
- ustalić mapowanie macierzy solvera na knob `matrix`,
- ustalić, czy wymagane jest `useMatrix`,
- ustalić kolejność oraz transpozycję wartości macierzy,
- ustalić znak i skalowanie `win_translate` przed włączeniem ręcznego principal point w etapie `8`,
- ustawić `focal`, `haperture`, `vaperture`,
- dodać funkcje `create_camera(result, options)` oraz `update_camera(node, result, options)`,
- nie importować `nuke` poza pakietem `nuke_integration`.

Test integracyjny uruchamiany wewnątrz Nuke:

- utworzyć syntetyczny `Camera2`,
- wygenerować dane solvera z oczekiwanych VP,
- utworzyć drugi `Camera2` przez adapter,
- porównać projekcję kilku punktów 3D,
- sprawdzić centralny principal point dla zakresu MVP.

Warunek zakończenia:

- projekcje kamer źródłowej i odzyskanej pokrywają się z ustaloną tolerancją.

## Etap 6 - dockowalny panel PySide2

Cel: dostarczyć użyteczny interfejs wewnątrz Nuke 15.1.

Zadania:

- zarejestrować panel przez `nukescripts.panels.registerWidgetAsPanel`,
- dodać komendę menu,
- pobrać zaznaczony node `Read`,
- odczytać format plate'a,
- wyświetlić podgląd plate'a w panelu (z obsługą EXR przez proxy),
- dodać cztery edytowalne odcinki VP na kanwie wewnątrz panelu,
- dodać uchwyt origin na kanwie wewnątrz panelu,
- dodać wybór osi świata,
- dodać sensor width i opcjonalnie sensor height,
- dodać podgląd komunikatów solvera,
- dodać `Create Camera` i `Update Camera`.

Warunek zakończenia:

- compositor może dopasować kamerę za pomocą panelu Lens Solver bez opuszczania Nuke.

## Etap 7 - Box Match

Cel: zapewnić intuicyjny tryb dopasowania kamery dla budynków i wnętrz.

Zadania:

- dodać wireframe prostopadłościanu jako element kanwy panelu,
- oznaczyć kierunki krawędzi kolorami osi świata: `X`, `Y`, `Z`,
- pozwolić przesuwać kontrolne narożniki boxa na kanwie,
- nie pozwalać przesuwać wszystkich ośmiu wierzchołków niezależnie,
- zachować spójną perspektywę i geometrię prostopadłościanu,
- wyprowadzać VP z grup krawędzi boxa i przekazywać je do solvera,
- pozwolić wybrać narożnik boxa jako origin,
- pozostawić ręczne linie VP jako tryb bazowy i diagnostyczny.

Warunek zakończenia:

- compositor może dopasować kamerę do bryły budynku lub wnętrza przez
  przeciąganie kontrolnych narożników boxa w panelu.

## Etap 8 - reference distance

Cel: nadać scenie znaczącą skalę.

Zadania:

- dodać wybór osi referencyjnej,
- dodać dwa uchwyty odcinka o znanej długości,
- wyznaczyć punkty 3D odcinka przez przecięcie promieni z odpowiednią płaszczyzną,
- przeskalować translację kamery,
- obsłużyć jednostki albo jasno przyjąć jednostki Nuke jako umowne.

Testy:

- odzyskanie długości odcinka syntetycznego,
- niepoprawne położenie uchwytów,
- prawie równoległe promienie.

## Etap 9 - principal point i dodatkowe tryby

Cel: rozszerzyć zakres scen obsługiwanych przez narzędzie.

Kolejność:

1. ręczny principal point,
2. lens shift przez `win_translate`,
3. principal point z trzeciego VP,
4. tryb `1VP` ze znaną ogniskową i horyzontem,
5. overlay siatki.

Każda funkcja wymaga osobnego testu regresyjnego.

## Etap 10 - trwałość ustawień i packaging

Cel: przygotować narzędzie do codziennej pracy.

Zadania:

- zapisywać ustawienia solvera w skrypcie Nuke,
- zdecydować między pomocniczym node'em `Group` a knobs kamery,
- dodać wersjonowanie serializowanego stanu,
- przygotować instalację przez `.nuke`, `NUKE_PATH` albo lokalny plugin path,
- dodać instrukcję instalacji,
- dodać przykładowy skrypt `.nk` oraz plate testowy, jeśli licencja assetu na to pozwala.

## Stan realizacji

- Etapy `0-2`: zakończone.
- Etapy `3-4`: zakończone.
- Etap `5`: zakończony dla centralnego principal point wymaganego przez MVP.
- Etap `6`: zakończony. Narzędzie operuje jako dockowalny panel PySide2 z interaktywną kanwą, obsługą zoomu/panningu, etykietami osi, siatką podłogi oraz kontrolkami HUD (Fit, 1:1, Grid, Reset).
- Etap `7`: zakończony. Dodano tryb dopasowania przez manipulację widocznymi krawędziami prostopadłościanu 3D na kanwie panelu (Box Match mode) z wyliczaniem linii w oparciu o solve.
- Następny krok: Etap `8` (reference distance) - dodanie wyboru osi referencyjnej oraz dwóch uchwytów odcinka o znanej długości w celu nadania scenie skali.
## Definicja ukończenia produktu v1

Wersja `v1` jest gotowa, gdy użytkownik Nuke 15.1 może dopasować statyczną kamerę `Camera2` w trybie `2VP`, ustawić origin oraz skalę referencyjną, zapisać stan w skrypcie Nuke i po ponownym otwarciu kontynuować pracę bez utraty ustawień.
