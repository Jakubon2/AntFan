# Testovací scénář AntFan

Postup, jak na Windows projít všechny funkce se skutečným hardwarem. Ke každému testu jsou kroky (**K**) a očekávaný výsledek (**O**). Výsledek si odškrtněte ☐ → ☑. Když něco nesedí, poznamenejte si číslo testu a pošlete soubor `%APPDATA%\AntFan\antfan.log`.

Scénář počítá s typickou sestavou: chytrý trenažér (ANT+ FE-C), tepový pás s ANT+, Rouvy a FTP 210 W. Čísla v testech části E si přepočítejte na své FTP.

**Celkem asi 60–75 minut**, z toho asi 25 minut na kole. Části A–D jdou bez šlapání.

---

## Příprava (5 min)
- [ ] Rouvy, Zwift a Garmin Express jsou zavřené, a to i v oznamovací oblasti u hodin.
- [ ] Ventilátor je zapnutý v zásuvce a v aplikaci Xiaomi Home je vidět online.
- [ ] Máte IP adresu a token ventilátoru (viz README, kapitola *Připojení ventilátoru*).
- [ ] Dongle je zapojený, ideálně přes prodlužovačku blízko kola.

---

## A. Spuštění (5 min)
**A1 – první spuštění**
- **K:** Dvojklik na `run.bat`.
- **O:** Poprvé se asi minutu instalují závislosti, pak se otevře okno AntFan. Okno se vejde na obrazovku a pravý panel není useknutý.

**A2 – druhá kopie**
- **K:** Při běžícím AntFan spusťte `run.bat` znovu.
- **O:** Hláška „AntFan už běží“ a druhé okno se neotevře.

**A3 – simulace**
- **K:** Zaškrtněte *Simulace* → **Hledat senzory** → po 6 s vyberte tepový pás a trenažér → **Spustit měření**.
- **O:**
  - Do 5 s se objeví 4 simulované senzory.
  - Po spuštění se hýbe výkon, tep i graf a ventilátor ukazuje stupeň.
- **K:** Odškrtněte *Simulace*.

---

## B. Ventilátor (10 min)
**B1 – špatná IP**
- **K:** Zadejte nesmyslnou IP (např. `192.168.1.250`) → **Test**.
- **O:** Do 3 s červeně „Ventilátor na … neodpovídá“.

**B2 – špatný token**
- **K:** Správná IP, v tokenu změňte poslední znak → **Test**.
- **O:** Červeně „neodpověděl na příkaz (špatný token…)“.

**B3 – správné údaje**
- **K:** Správná IP i token → **Uložit a připojit** → **Test**.
- **O:** Zeleně `OK: dmaker.fan.1c (fw …), vypnuto/zapnuto, stupeň …`.

**B4 – vypnuté pípání a podsvícení**
- **K:** Nechte zaškrtnuté *Vypnout pípání* i *Vypnout podsvícení*. Přepněte na **Ručně** a klikejte 1 → 2 → 3 → Vyp, mezi kliky 3 s.
- **O:**
  - Ventilátor mění rychlost bez pípnutí a podsvícení je zhasnuté.
  - Stav „skutečně“ v dlaždici ventilátoru odpovídá.

**B5 – zapnutí pípání zpět**
- **K:** Odškrtněte *Vypnout pípání* a klikněte na 1 a 2.
- **O:** Ventilátor pípá. Pak *Vypnout pípání* znovu zaškrtněte.

**B6 – změna ovladačem**
- **K:** V ručním režimu nastavte 2 a ovladačem nebo tlačítkem na ventilátoru přepněte na 3.
- **O:** Do 15 s AntFan vrátí stupeň 2.

**B7 – výpadek napájení**
- **K:** Vytáhněte ventilátor ze zásuvky na 30 s a pak ho zapojte.
- **O:**
  - Během výpadku se zobrazí červená chyba.
  - Po zapojení a připojení k Wi-Fi (asi 30–60 s) se AntFan připojí sám, nastaví stupeň a znovu ztiší pípání.

---

## C. Vyhledání senzorů (5 min)
**C1 – vyhledání**
- **K:** Nasaďte a navlhčete pás, zapněte trenažér a protočte kliky → **Hledat senzory**.
- **O:**
  - Do 15 s je vidět **Tepový pás** a **Trenažér** s ID a živou hodnotou. Tep odpovídá skutečnosti a výkon se mění při šlapání.
  - Pokud **pás chybí**, nejspíš nevysílá ANT+ (Polar H10 umí jen Bluetooth). Poznamenejte si model.
  - Pokud **trenažér chybí**, ověřte v manuálu, že vysílá ANT+ FE-C.

**C2 – rozpoznání svých zařízení**
- **K:** Přestaňte šlapat a sundejte pás.
- **O:** Hodnoty u vašich senzorů zmizí („–“) nebo spadnou. Cizí senzory (sousedů) se nemění.

**C2b – kvalita příjmu**
- **K:** Vyberte pás a trenažér → **Spustit měření** → 2 min šlapejte stálým tempem.
- **O:**
  - Ve sloupci *Příjem* je u obou senzorů 90–100 %.
  - Graf výkonu nemá propady na 0. Případný krátký výpadek se projeví jen nápisem „⚠ výpadek příjmu“ u výkonu.
  - Když je příjem pod 80 %, dejte dongle na prodlužovačce blíž ke kolu a porovnejte.
- **K:** Místo *Powermetru* vyberte *Trenažér* se stejným ID (nebo naopak) a zopakujte.
- **O:** Poznamenejte si, která varianta má lepší příjem.

**C3 – zapamatování výběru**
- **K:** Vyberte pás a trenažér (☑) a zavřete a znovu otevřete AntFan.
- **O:** Oba jsou v seznamu zaškrtnuté i bez vyhledávání.

---

## D. Odolnost donglu (10 min)
**D1 – dongle drží jiný program**
- **K:** Spusťte Rouvy a nechte ho najít trenažér přes **ANT+**. V AntFan dejte **Spustit měření**.
- **O:**
  - AntFan to zkusí 4× (stavový řádek „zkouším znovu 2/4…“).
  - Pak ukáže hlášku, že dongle drží jiný program, a v seznamu uvede **ROUVY**.

**D2 – uvolnění**
- **K:** Rouvy úplně zavřete → **Spustit měření**.
- **O:** Měření běží bez přepojování donglu.

**D3 – vytažení za běhu**
- **K:** Během měření vytáhněte dongle a za 10 s ho zapojte.
- **O:** Hláška „Dongle byl odpojen – zapojte ho znovu“. Po zapojení se měření do pár sekund samo obnoví.

**D4 – tlačítko Reset**
- **K:** Během měření klikněte na **⟲ Reset donglu**.
- **O:** „Resetuji dongle…“ a pak se měření samo obnoví.

**D5 – násilné ukončení**
- **K:** Ve Správci úloh ukončete AntFan (`pythonw.exe` nebo `AntFan.exe`) a hned ho spusťte znovu.
- **O:** Měření jde spustit bez přepojení donglu a bez hlášky o jiné aplikaci.

---

## E. Řízení na kole (25 min)
Nastavení: **Automaticky**, režim **Chytře**, záložka *Prahy* → **% FTP**, FTP **210**, max. tep (váš skutečný, jinak 185), prahy 30 / 60 / 85 %. Vedle prahů by mělo být ≈ 63 / 126 / 178 W.

**E1 – zvyšování podle výkonu**
- **K:**
  - 3 min šlapejte ~100 W.
  - Pak 3 min ~150 W.
  - Pak 4 min ~200 W.
- **O:**
  - Při ~100 W stupeň **1**, při ~150 W stupeň **2** a při ~200 W stupeň **3**.
  - Každé zvýšení přijde do ~10 s od změny výkonu (vyhlazení).

**E2 – tep drží stupeň (chytrý režim)**
- **K:** Hned po 200 W šlapejte 90 s lehce (~100 W).
- **O:**
  - Stupeň **neklesne na 1**. Tep ho podrží na stupni, který odpovídá tepu, s důvodem „tep drží stupeň“.
  - Při tepu nad ~130 bpm je to stupeň 2. Stupeň 3 drží jen tep nad ~152 bpm (při max. tepu 185).
  - Na 1 klesne, až tep spadne pod ~125 bpm, a ještě 20 s počká.

**E3 – srovnání s režimem jen výkon**
- **K:** Přepněte *Řídit podle* na **Jen výkon** a zopakujte 2 min ~200 W a 90 s ~100 W.
- **O:** Asi 20 s po poklesu výkonu stupeň klesne na **1** (prodleva). Pak vraťte **Chytře**.

**E4 – hystereze**
- **K:** Šlapejte těsně kolem prahu stupně 3, tedy střídavě 170–190 W, 2 minuty.
- **O:** Jakmile stupeň 3 naskočí, drží se. Klesl by až při průměru pod ~158 W (178 W minus hystereze 20 W) trvajícím 20 s. Stupeň nepřeskakuje sem a tam.

**E5 – přestávka v šlapání**
- **K:** 10 s nešlapejte a pak pokračujte.
- **O:** Výkon do 4 s ukáže 0 W, ale stupeň v tak krátké pauze neklesne.

**E6 – dofukování**
- **K:** Ukončete trénink: přestaňte šlapat a sundejte pás.
- **O:**
  - Asi 20 s po zastavení se ve stupni ventilátoru objeví „dofukování ještě 2:xx“ a ventilátor běží na stupni 1.
  - Po ~3 min se vypne.
- **Pozn.:** Když pás po tréninku necháte na sobě, ventilátor fouká, dokud tep neklesne pod ~97 bpm, a teprve pak začne dofukování.

**E7 – dofukování vypnuto**
- **K:** *Chování* → Dofukování **0** → Použít. Šlapejte 1 min, pak přestaňte a sundejte pás.
- **O:** Po ~20–30 s se ventilátor vypne bez dofukování. Pak vraťte 3 min.

**E8 – přepočet FTP**
- **K:** Změňte FTP na 250 → Použít.
- **O:** Přepočty u prahů se změní na ≈ 75 / 150 / 212 W a dlaždice výkonu ukazuje nové % FTP. Pak vraťte 210.

**E9 – jen tep**
- **K:** *Řídit podle* → **Jen tep**. Šlapejte, až tep stoupne nad ~130 bpm.
- **O:** Stupeň sleduje tep se zpožděním. Pak vraťte **Chytře**.

---

## F. Souběh s Rouvy (10 min, volitelné)
**F1 – Rouvy přes Bluetooth, AntFan přes ANT+**
- **K:** V Rouvy připojte trenažér a pás přes **Bluetooth** (ne ANT+). Spusťte AntFan → **Spustit měření** a pak v Rouvy jízdu.
- **O:**
  - Obě aplikace ukazují výkon i tep a hodnoty se shodují (±5 W, ±2 bpm).
  - Rouvy dál řídí odpor trenažéru.
  - Pokud AntFan výkon z trenažéru během připojení přes Bluetooth nevidí, trenažér souběžně ANT+ nevysílá. Řešením je druhý ANT+ dongle.

**F2 – celý trénink**
- **K:** Odjeďte normální trénink v Rouvy s AntFan na pozadí.
- **O:** Program po celou dobu reaguje, graf běží a v logu nejsou chyby (`ERROR`).

---

## Co poslat, když něco nefunguje
1. Číslo testu a co se stalo místo očekávaného výsledku.
2. Soubor `%APPDATA%\AntFan\antfan.log`.
3. Snímek obrazovky AntFan (Win+Shift+S).
4. Pro testy v části E případně FIT soubor z Rouvy z té jízdy.
