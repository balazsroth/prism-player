# Prism Player

Modern, **Liquid Glass** felületű médialejátszó a hivatalos **LibVLC** motorra építve – minden formátum, amit a VLC ismer, hardveres gyorsítással.

## Telepítés

1. Töltsd le a legfrissebb **Prism-Setup-3.0.exe** telepítőt a [Releases](../../releases/latest) oldalról.
2. Futtasd (rendszergazdai jog nem kell), és kövesd a varázslót.

Windows 10/11 (x64) szükséges.

## Menük

* **Média** – fájl, több fájl, mappa, lemez (DVD / Blu-ray / Audio CD / VCD), hálózati adatfolyam, rögzítőeszköz (képernyő, webkamera), URL a vágólapról, hálózati források és médiatár (saját mappák, UPnP/DLNA, SAP, mDNS, podcastok), legutóbbi média, lejátszási lista mentése (M3U), konvertálás / mentés, adatfolyam küldése (HTTP stream), kilépés a lista végén
* **Lejátszás** – cím, fejezet és program (DVD/Blu-ray/MKV/DVB), lemezmenü-navigáció, egyéni könyvjelzők, sebesség (0.25x–4x), kis / normál / nagy ugrás, ugrás időpontra, képkocka léptetés, ismétlés (ki / összes / egy szám), véletlenszerű lejátszás, A-B ismétlés, felvétel, lejátszás Chromecast-eszközön
* **Hang** – hangsáv, hangeszköz, sztereó mód, spektrum vizualizáció, hangerő (200%-ig), hangszínszabályzó, hangeffektek (kompresszor, térhatás, hangmagasság, normalizálás, karaoke, mono), hang késleltetés
* **Videó** – videósáv, teljes képernyő, mindig legfelül, nagyítás, képarány, levágás, deinterlace (10 mód), forgatás és tükrözés, videószűrők (élesítés, zajszűrés, szépia, elmosás, régi film…), logó a videón, pillanatkép
* **Felirat** – feliratfájl betöltése, online feliratkeresés (OpenSubtitles), feliratsáv, felirat késleltetés, megjelenés (betűtípus, méret, szín, körvonal, háttér, karakterkódolás), teletext
* **Eszközök** – effektek és szűrők (10 sávos equalizer + előerősítés, videó képbeállítások, sávszinkronizálás), média- és kodekinformációk, üzenetnapló, webes távirányító, testreszabható billentyűparancsok, beállítások (haladó LibVLC-opciókkal)
* **Nézet** – lejátszási lista, minimalista nézet

További kényelmi funkciók: folytatás ott, ahol abbahagytad; a legutóbbi média, a hangerő és az ismétlési mód megjegyzése; képernyőn megjelenő visszajelzések (OSD); a lejátszási lista átrendezése húzással, jobb klikkes menüvel és Delete billentyűvel; Drag & Drop fájlokra és mappákra.

Windows-integráció:
* **Egy ablak**: ha a Prism már fut, az Intézőből megnyitott fájlok ebbe kerülnek, nem nyílik új ablak (Beállítások → Általános, kikapcsolható).
* **Médiabillentyűk és a Windows médiavezérlője**: a billentyűzet lejátszás/szünet, következő, előző és leállítás gombjai működnek, a hangerő-felugró ablakban és a zárolási képernyőn is látszik a cím és a vezérlés.
* **Tálca**: az ikon előnézetében előző / lejátszás-szünet / következő gomb, az ikonon a lejátszás állapota (sárga, ha szünetel).
* **Fájltársítás**: Beállítások → Általános → Hozzáadás a Windowshoz. A Prism bekerül a fájlok „Társítás” menüjébe és a Windows alapértelmezett alkalmazásai közé; alapértelmezett lejátszónak a Windows Gépházban lehet kiválasztani (az „Alapértelmezett alkalmazások...” gomb oda visz). Az EXE-ből érdemes elvégezni, mert mindig az a példány lesz bejegyezve, amelyikből a gombot megnyomod.

## Gyorsbillentyűk

A teljes lista a programban: **Súgó → Billentyűparancsok (F1)**; mindegyik átállítható: **Eszközök → Billentyűparancsok testreszabása**. A legfontosabbak:

| Billentyű | Művelet |
|---|---|
| Szóköz | Lejátszás / Szünet |
| Balra / Jobbra | Ugrás 10 mp (Shift: 3 mp, Ctrl: 1 perc) |
| Felfelé / Lefelé | Hangerő ±5% |
| `[` / `]` / `=` | Lassabb / Gyorsabb / Normál sebesség |
| F / Escape | Teljes képernyő / kilépés belőle |
| M | Némítás |
| N / P | Következő / Előző |
| L / R | Ismétlési mód / Véletlenszerű |
| A / C / Z / D | Képarány / Levágás / Nagyítás / Deinterlace |
| B / V | Hangsáv / Feliratsáv váltása |
| Shift + S | Pillanatkép |
| Ctrl + E | Effektek és szűrők |
| Shift + R | Felvétel indítása / leállítása |
| Shift + M | Lemezmenü (DVD / Blu-ray) |
| Ctrl + M | Üzenetek |

## Fájlok

- **Telepítő**: a Releases oldalon (`Prism-Setup-3.0.exe`; építve: `installer/`) – a saját felhasználónak telepít (rendszergazdai jog nélkül, kérésre minden felhasználónak), Start menü és asztali parancsikon, fájltársítás, eltávolítás a Gépház → Alkalmazások alól
- **Futtatható program**: `dist/Prism/Prism.exe` – a teljes `dist/Prism` mappával együtt működik (`_internal`, `libvlc*.dll`, `plugins`); a buildhez a LibVLC 3.x Windows x64 `libvlc.dll`, `libvlccore.dll` és `plugins` mappája kell a `vlc_runtime` mappába (a hivatalos VLC 3.x zip-ből)
- **Forráskód**: `main.py`, `main_window.py`, `dialogs.py`, `advanced_dialogs.py`, `vlc_player.py`, `vlc_vars.py`, `playlist_manager.py`, `remote_control.py`, `subtitle_search.py`, `win_integration.py`, `liquid_widgets.py`, `liquid_theme.py`
- **Függőségek a forrásból futtatáshoz**: `PyQt6`, `python-vlc`, a médiavezérlőhöz `winrt-Windows.Media.Playback`, `winrt-Windows.Media`, `winrt-Windows.Foundation`, `winrt-Windows.Foundation.Collections`, `winrt-Windows.Storage.Streams`, `winrt-Windows.Storage` (ezek nélkül is fut, csak médiabillentyűk nélkül)
- **EXE és telepítő építése**: `python build_exe.py` – kódváltoztatás után mindig építsd újra; a telepítőhöz Inno Setup 6 kell (`winget install JRSoftware.InnoSetup`), a szkriptje a `Prism.iss`

## Megjegyzések

* **Webes távirányító**: Eszközök → Webes távirányító; a megjelenő címet (pl. `http://192.168.1.10:8090/`) nyisd meg a telefonod böngészőjében. Port és jelszó: Beállítások → Távvezérlés és online.
* **Online feliratok**: ingyenes OpenSubtitles.com API-kulcs kell (opensubtitles.com/consumers), a letöltéshez OpenSubtitles-fiók is.
* **Felvétel**: a forrást átkódolás nélkül menti a Beállításokban megadott mappába (alapból `Videók\Prism`).
* **Nem elérhető** (a LibVLC 3 nem támogatja beágyazott lejátszóban): Lua-bővítmények (pl. VLsub – helyette a beépített online feliratkereső van), két felirat egyszerre, VLM, falkép/klónozás külön ablakokban, macOS/Linux.

## Licenc

GNU Affero General Public License v3.0 - lásd a [LICENSE](LICENSE) fájlt. A Prism a LibVLC-t (LGPL) és a PyQt6-ot (GPL) használja.

