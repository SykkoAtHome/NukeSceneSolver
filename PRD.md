# Nuke Scene Solver - PRD

## Status dokumentu

- Etap: inicjalizacja projektu
- Docelowe środowisko: Foundry Nuke 15.1
- Technologia: Python 3.10 + PySide2 dostarczane z Nuke 15.1
- Data utworzenia: 2026-05-31

## Cel produktu

Stworzyć natywne narzędzie dla Foundry Nuke 15.1, które pozwala dopasować kamerę 3D do pojedynczego nieruchomego obrazu na podstawie linii perspektywy wskazanych przez użytkownika.

Narzędzie ma działać wewnątrz Nuke i tworzyć lub aktualizować standardowy node `Camera2`, gotowy do użycia z typowym workflow Nuke, między innymi `Project3D`, `ScanlineRender` i sceną 3D.

## Główne założenie

Projekt powstaje od zera dla Nuke. Nie jest wrapperem, importerem ani portem fSpy. Nie importuje plików `.fspy` i nie zależy od aplikacji fSpy.

Repozytorium referencyjne `D:\code\fspy` było użyte wyłącznie do rozpoznania oczekiwanego zakresu funkcjonalnego i znalezienia literatury dotyczącej geometrii punktów zbiegu. Implementacja solvera musi być samodzielna: własne modele danych, własna struktura kodu, własne równania zapisane na podstawie geometrii projekcyjnej i własne testy.

Punktem odniesienia matematycznego jest publikacja:

> E. Guillou, D. Meneveaux, E. Maisel, K. Bouatouch, "Using Vanishing Points for Camera Calibration and Coarse 3D Reconstruction from a Single Image".

Lokalna kopia publikacji znajduje się w:

`D:\code\fspy\doc\Using Vanishing Points for Camera Calibration.pdf`

## Problem użytkownika

W compositingu często potrzebna jest przybliżona kamera 3D pasująca do perspektywy pojedynczego plate'a, ale pełny camera tracking jest zbędny albo niemożliwy. Użytkownik powinien móc wskazać linie należące do kierunków sceny i otrzymać kamerę Nuke zgodną z obrazem.

## Użytkownik docelowy

Compositor lub generalista VFX pracujący w Nuke 15.1, który chce szybko:

- dopasować kamerę do zdjęcia albo pojedynczej klatki,
- wykonać prostą rekonstrukcję przestrzeni,
- użyć projekcji 3D,
- ustawić geometrię pomocniczą zgodnie z perspektywą plate'a.

## Zakres MVP

Pierwsza użyteczna wersja obsługuje tryb `2VP`:

1. Użytkownik wybiera node `Read` albo wskazuje plate w panelu.
2. Panel pokazuje obraz i cztery edytowalne odcinki:
   - dwa odcinki wyznaczające pierwszy punkt zbiegu,
   - dwa odcinki wyznaczające drugi punkt zbiegu.
3. Kierunki reprezentowane przez oba punkty zbiegu są do siebie prostopadłe w świecie 3D.
4. Użytkownik wskazuje punkt `origin` widoczny na obrazie.
5. Solver oblicza:
   - oba punkty zbiegu,
   - względną ogniskową,
   - poziomy i pionowy FOV,
   - orientację kamery,
   - domyślną pozycję kamery względem origin.
6. Panel tworzy nowy node `Camera2` albo aktualizuje istniejący.
7. Panel pokazuje błędy i ostrzeżenia dla konfiguracji zdegenerowanych lub niestabilnych numerycznie.

## Funkcje po MVP

Kolejne wersje mogą dodać:

- jawny wybór osi świata dla obu VP, na przykład `+X`, `-X`, `+Y`, `-Y`, `+Z`, `-Z`,
- ręczny principal point,
- principal point obliczany z trzeciego VP,
- tryb `1VP` ze znaną ogniskową i sensorem oraz ręcznie ustawianym horyzontem,
- Box Match: ograniczony wireframe prostopadłościanu dopasowywany w Viewerze,
- reference distance do nadania scenie rzeczywistej skali,
- overlay osi oraz siatki,
- zapis oraz odczyt ustawień projektu w knobs node'a lub osobnym JSON,
- aktualizację kamery na żywo podczas przeciągania uchwytów,
- obsługę proxy i różnic między formatem plate'a a formatem projektu.

## Poza zakresem

Projekt nie ma realizować:

- importu projektów `.fspy`,
- uruchamiania fSpy jako procesu zewnętrznego,
- kopiowania kodu TypeScript z fSpy,
- camera trackingu wielu klatek,
- estymacji lens distortion,
- automatycznego wykrywania linii obrazu w pierwszej wersji,
- pluginu C++ albo NDK w pierwszej wersji.

Plate powinien być wcześniej undistorted. Solver zakłada model kamery pinhole.

## UX i integracja z Nuke 15.1

Pierwsza wersja ma mieć dockowalny panel PySide2 rejestrowany w Nuke oraz
uchwyty edycyjne bezpośrednio na obrazie aktywnego Viewera. Panel zawiera
ustawienia, komunikaty solvera i akcje kamery. Linie VP oraz origin należy
ustawiać w Viewerze, a nie na osobnej kopii plate'a w panelu.

Docelowy przepływ:

1. Zaznacz `Read`.
2. Otwórz panel `Scene Solver`.
3. Kliknij `Use Selected Read`.
4. Ustaw odcinki VP oraz origin.
5. Wybierz mapowanie osi świata.
6. Kliknij `Create Camera` albo `Update Camera`.
7. Zweryfikuj dopasowanie na siatce lub geometrii testowej.

Viewer overlay oraz obsługa myszy mogą zostać zaimplementowane w Pythonie.
Plugin C++ albo NDK pozostaje poza zakresem pierwszej wersji.

Po bazowym trybie linii VP należy dodać `Box Match` jako główny workflow dla
budynków i wnętrz. Użytkownik dopasowuje kontrolne narożniki wireframe boxa,
natomiast pozostałe wierzchołki wynikają z ograniczeń prostopadłościanu i
spójnej perspektywy. Nie wolno traktować ośmiu narożników jako niezależnych
punktów 2D. Krawędzie boxa dostarczają solverowi grup linii dla osi `X`, `Y`
oraz `Z`, a wybrany narożnik może pełnić rolę origin.

## Parametry Camera2

Adapter Nuke powinien ustawiać standardowy node `Camera2`. Minimalny zestaw parametrów do zbadania i kontrolowania:

- `focal`
- `haperture`
- `vaperture`
- `win_translate`
- `useMatrix`
- `matrix`

Nie wolno zakładać konwencji macierzy ani znaków na podstawie Blendera lub innej aplikacji. Mapowanie osi świata, kolejność macierzy, transpozycja oraz kierunek `win_translate` muszą zostać ustalone przez testy projekcji wykonane w Nuke 15.1.

Podstawowa relacja dla sensora poziomego:

```text
focal_mm = 0.5 * horizontal_aperture_mm * relative_focal_length
```

Domyślny sensor MVP może mieć szerokość `36 mm`, ale użytkownik powinien móc go zmienić.

## Model danych solvera

Solver nie powinien importować modułu `nuke`. Dzięki temu można testować matematykę poza Nuke.

Przykładowe wejście:

```python
SolveInput(
    image_width=1920,
    image_height=1080,
    vp1_segments=(segment_a, segment_b),
    vp2_segments=(segment_c, segment_d),
    principal_point=None,
    origin=Point2D(0.5, 0.5),
    first_axis="+X",
    second_axis="+Y",
    sensor_width_mm=36.0,
)
```

Przykładowy wynik:

```python
SolveResult(
    camera_matrix=matrix_4x4,
    relative_focal_length=value,
    horizontal_fov_radians=value,
    vertical_fov_radians=value,
    principal_point=point,
    vanishing_points=(vp1, vp2, vp3),
    warnings=[],
    errors=[],
)
```

Współrzędne uchwytów UI powinny być przechowywane jako wartości względne obrazu w zakresie `[0, 1]`. Solver powinien jawnie konwertować je na własny układ współrzędnych płaszczyzny obrazu.

## Wymagania jakościowe

- Core matematyczny bez zależności od Nuke i Qt.
- Czytelne typy danych, najlepiej `dataclasses`.
- Brak niejawnych konwersji układów współrzędnych.
- Walidacja dzielenia przez zero, linii równoległych, niepoprawnej ogniskowej i macierzy o złym wyznaczniku.
- Testy jednostkowe dla geometrii 2D i solvera.
- Test integracyjny uruchamiany wewnątrz Nuke 15.1 dla `Camera2`.
- Dokumentacja konwencji osi oraz macierzy.

## Kryteria akceptacji MVP

MVP jest gotowe, gdy:

1. Panel można otworzyć z menu Nuke 15.1.
2. Panel potrafi pobrać format i obraz ze wskazanego `Read`.
3. Użytkownik może edytować cztery odcinki VP i origin.
4. Solver zwraca stabilny wynik dla poprawnych danych syntetycznych.
5. Kliknięcie `Create Camera` tworzy standardowy `Camera2`.
6. Rzut prostego boxa albo siatki z utworzonej kamery pokrywa się z syntetycznym plate'em użytym w teście.
7. Niepoprawne dane powodują czytelny błąd zamiast wyjątku albo macierzy z wartościami `NaN`.

## Otwarte decyzje

Do rozstrzygnięcia w trakcie implementacji:

- jaki Pythonowy mechanizm overlay i obsługi myszy w Viewerze zastosować dla uchwytów VP oraz origin,
- jak pobierać obraz z `Read` bez kosztownego renderowania całej sekwencji,
- czy ustawienia sesji zapisywać w knobs pomocniczego node'a `Group`, czy w osobnym pliku JSON,
- czy Box Match ma dodatkowo tworzyć pomocniczą geometrię `Cube` do walidacji,
- jaka domyślna odległość kamery od origin jest najbardziej ergonomiczna bez reference distance.

## Materiały referencyjne

- Repo użyte do analizy funkcjonalnej: `D:\code\fspy`
- Publikacja: `D:\code\fspy\doc\Using Vanishing Points for Camera Calibration.pdf`
- Dokumentacja dockowalnych paneli Nuke 15.1: https://learn.foundry.com/nuke/developers/15.1/pythondevguide/_modules/nukescripts/panels.html
- Dokumentacja kamery Nuke: https://learn.foundry.com/nuke/content/reference_guide/3d_nodes/camera.html

## Instrukcja dla kolejnej sesji

Przeczytaj najpierw ten dokument oraz `PLAN.md`. Rozpocznij implementację od core matematycznego i testów syntetycznych. Nie dodawaj zależności od repo `D:\code\fspy` i nie kopiuj z niego implementacji.
