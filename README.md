# AntFan – ventilátor řízený výkonem a tepem (ANT+)

Program pro Windows 10/11 a macOS (Apple Silicon):

1. připojí se k ANT+ USB donglu,
2. vyhledá všechny tepové pásy, powermetry a chytré trenažéry (ANT+ FE-C) v okolí,
3. u vybraných zobrazuje výkon, kadenci a tep v reálném čase (s grafem za posledních 10 minut),
4. podle hodnot nastavuje rychlost ventilátoru **Xiaomi Smart Standing Fan 2 Lite** (`dmaker.fan.1c`, stupně 1–3) přes lokální Wi-Fi.

## Podporovaná zařízení

| Zařízení | Funguje | Nefunguje |
|---|---|---|
| **ANT+ dongle** | Garmin ANT+ USB stick (ANTUSB2, `0fcf:1008`), Garmin mini stick (ANTUSB-m, `0fcf:1009`) a většina levných klonů (CooSpo, CYCPLUS, Anself…), které se hlásí stejně | starý stick první generace (`0fcf:1004`), Bluetooth |
| **Tepový pás** | jakýkoli s ANT+: Garmin HRM, Wahoo TICKR, Scosche Rhythm+, Garmin hodinky se zapnutým *vysíláním tepu* | jen Bluetooth: Polar H9, H10, Verity Sense |
| **Powermetr** | jakýkoli ANT+: pedály (Garmin Rally, Favero Assioma), kliky (Stages, 4iiii, Quarq) | jen Bluetooth |
| **Chytrý trenažér** | jakýkoli s ANT+ FE-C: Tacx, Wahoo KICKR, Elite, Zwift Hub… | trenažér jen s Bluetooth |
| **Ventilátor** | Xiaomi Smart Standing Fan 2 Lite (`dmaker.fan.1c`), odzkoušený | starší Xiaomi se starým protokolem, ventilátory s plynulou rychlostí v %, jiné značky |
| **Počítač** | Windows 10 a 11, macOS 11+ na Macu s Apple Silicon (M1 a novější), viz [macOS](#macos) | Mac s procesorem Intel (sestavení je jen pro arm64), Linux zatím ne |

Samostatné čidlo rychlosti a kadence AntFan nepoužívá, kadenci bere z powermetru nebo trenažéru.

**Jiné Xiaomi ventilátory:** novější modely s protokolem MIoT a stupni rychlosti (1–5) by měly jít, ale nikdo je nezkoušel. V `%APPDATA%\AntFan\config.json` (na macOS `~/Library/Application Support/AntFan/config.json`) je potřeba v sekci `fan` upravit `max_level` a čísla vlastností (`power_siid/piid`, `level_siid/piid`, `buzzer_…`, `light_…`) podle specifikace modelu na <https://home.miot-spec.com>. Když to u vás funguje, napište model a hodnoty do Issues.

## Instalace

### 1. Program
**Nejjednodušší:** v sekci [Releases](../../releases) stáhněte **`AntFan.exe`** a spusťte ho. Python ani nic dalšího není potřeba.

Exe sestavuje GitHub Actions (`.github/workflows/build-exe.yml`) při každé značce verze `v*` a před vydáním ho ověří vestavěnou kontrolou (`AntFan.exe --selftest`).

**Ze zdrojového kódu:** nainstalujte Python 3.10+ z <https://www.python.org/downloads/windows/> (zaškrtněte *Add python.exe to PATH*) a spusťte `run.bat`.

### 2. Ovladač ANT+ donglu
Program komunikuje s donglem přes libusb, takže dongle potřebuje ovladač **libusbK** nebo **WinUSB**.
Pokud už máte libusbK (např. kvůli GoldenCheetah), nemusíte nic měnit.

Jinak: stáhněte [Zadig](https://zadig.akeo.ie/), *Options → List All Devices*, vyberte „ANT USBStick2“ (nebo „ANT USB-m Stick“), zvolte **libusbK** a klikněte na *Replace Driver*.

> Pozor: Garmin Express a některé aplikace používají vlastní ovladač. Po přepnutí na libusbK je nemusí vidět. Zwift, TrainerRoad a podobné aplikace musí být při spuštění AntFan zavřené, protože dongle může používat jen jeden program najednou.

### 3. Spuštění
Dvojklik na **`AntFan.exe`**, nebo u verze ze zdrojového kódu na **`run.bat`**. Při prvním spuštění `run.bat` se vytvoří virtuální prostředí a nainstalují závislosti (cca 1 minuta).

Exe si můžete sestavit i sami: spusťte **`build_exe.bat`**, výsledek najdete v `dist\AntFan.exe`.

## macOS

Aplikace pro Mac s Apple Silicon (M1 a novější). Ovladač donglu se na Macu neinstaluje ani nemění, Zadig není potřeba.

1. V sekci [Releases](../../releases) stáhněte **`AntFan-macOS.zip`** a rozbalte ho (dvojklik).
2. **`AntFan.app`** přetáhněte do složky *Aplikace*.
3. **První spuštění:** aplikace není podepsaná u Applu, takže ji macOS dvojklikem neotevře. Klikněte na ni **pravým tlačítkem → Otevřít** a v dialogu znovu *Otevřít*. Další spuštění už jde normálně.
   Když macOS hlásí, že je aplikace „poškozená“ nebo ji nejde otevřít ani takhle, odstraňte příznak stažení v Terminálu:
   ```bash
   xattr -dr com.apple.quarantine /Applications/AntFan.app
   ```
4. Zapojte ANT+ dongle (na USB-C přes redukci) a spusťte měření.

Dongle může naráz používat jen jedna aplikace. Zwift, ROUVY, TrainerRoad, Garmin Express apod. musí dongle pustit, jinak AntFan hlásí, že je obsazený (a vypíše, který program běží). Garmin Express a Zwift Launcher běží na pozadí i po zavření okna, zkontrolujte ikonky v horní liště.

Nastavení a log jsou v `~/Library/Application Support/AntFan/` (Nastavení → Diagnostika → *Otevřít složku s logem*).

**Ze zdrojového kódu:** Python 3.10+ z <https://www.python.org/downloads/macos/> (obsahuje tkinter), pak v Terminálu ve složce projektu:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m antfan
```

## Připojení ventilátoru (IP adresa a token)

### Jak to funguje
AntFan posílá příkazy ventilátoru **přímo v domácí síti** (UDP port 54321), bez cloudu Xiaomi. Komunikace je šifrovaná **tokenem**: tajným klíčem o 32 hex znacích, který ventilátor vytvoří při spárování s aplikací Xiaomi Home. Bez správného tokenu ventilátor příkazy ignoruje.
Aplikace Xiaomi Home i dálkový ovladač fungují dál normálně vedle AntFan.

### Postup
1. **Spárujte ventilátor** v aplikaci Xiaomi Home (Mi Home), pokud už není. Ventilátor umí jen Wi-Fi 2,4 GHz a PC musí být ve stejné síti. Síť pro hosty často zařízení navzájem izoluje.
2. **Získejte token** nástrojem [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor):
   - V sekci *Releases* stáhněte `token_extractor.exe` a spusťte ho.
   - **Nejjednodušší je přihlášení QR kódem** (nabízí ho novější verze nástroje). Nástroj ukáže QR kód a ten naskenujete v aplikaci Xiaomi Home, ve které jste přihlášení. Heslo není potřeba.
   - Druhá možnost je jméno a heslo k Xiaomi účtu. Účet se zadává jen do tohoto nástroje, AntFan ho nikdy nepotřebuje.
   - Pokud se nástroj zeptá na oblast serveru, pro Evropu to bývá `de`. Když vypíše 0 zařízení, nechte oblast prázdnou a nástroj projde všechny.

   **Když heslo nejde:**
   - Pokud se do Xiaomi Home přihlašujete přes Google, Apple nebo Facebook, účet **nemá heslo**. Použijte QR kód, nebo si heslo nastavte na <https://account.xiaomi.com> (přihlaste se stejným způsobem → Zabezpečení → heslo).
   - Jako jméno použijte e-mail, telefon s předvolbou (`+420…`) nebo číselné Xiaomi ID (v aplikaci Xiaomi Home → Profil).
   - Heslo si ověřte přihlášením na <https://account.xiaomi.com>. Když nejde ani tam, použijte „Zapomenuté heslo“.
   - Při chybě captcha nebo nekonečném ověření ve dvou krocích stáhněte nejnovější verzi nástroje, zkontrolujte spam (kód chodí e-mailem) a nezkoušejte to mnohokrát za sebou, protože Xiaomi pokusy denně omezuje. Pomůže i QR kód.

   **Když extractor nefunguje vůbec, zkuste program `micloud`.** Jde o jinou implementaci téhož přihlášení a nainstalujete ho do Pythonu, který si vytvořil AntFan. Nejdřív aspoň jednou spusťte `run.bat`, pak v příkazovém řádku ve složce AntFan zadejte:
   ```bat
   .venv\Scripts\pip install micloud
   .venv\Scripts\micloud get-devices -c de --pretty
   ```
   - Program se zeptá na jméno (Username) a heslo (Password). Heslo se při psaní nezobrazuje.
   - Vypíše zařízení. U ventilátoru (`"model": "dmaker.fan.1c"`) opište hodnoty `"localip"` a `"token"`.
   - Když vypíše prázdný seznam `[]`, zkuste jinou oblast místo `de`: `i2`, `ru`, `sg`, `us` nebo `cn`.
   - `micloud` neumí ověření ve dvou krocích. Když při správném hesle hlásí „Access denied“, Xiaomi pokus nejspíš zablokoval jako podezřelé přihlášení. Potvrďte ho v e-mailu nebo v aplikaci Xiaomi Home a zkuste to znovu.
   - Nástroj vypíše všechna zařízení. U ventilátoru (model `dmaker.fan.1c`) si zkopírujte **IP** a **TOKEN**.
3. **Nastavte pevnou IP:** v routeru ventilátoru zarezervujte IP adresu (DHCP rezervace podle MAC adresy). Jinak se adresa může po restartu routeru změnit.
4. **V AntFan** vyplňte IP a token, klikněte na **Uložit a připojit** a pak na **Test**. Mělo by se zobrazit `OK: dmaker.fan.1c, …`.

Token se změní, když ventilátor resetujete nebo znovu spárujete. Pak ho získejte znovu.

### Pípání a podsvícení
Ventilátor jinak pípne při každém příkazu, proto ho AntFan při připojení ztiší (volba **Vypnout pípání**). Volitelně vypne i podsvícení. Nastavení se pošle při každém připojení a po výpadku ventilátoru. Když políčko odškrtnete, pípání nebo podsvícení se zase zapne.

## Připojení senzorů ANT+
1. Zapojte dongle, ideálně přes **USB prodlužovačku** blízko kola. Dosah je pár metrů a porty USB 3 ruší rádio 2,4 GHz.
2. **Probuďte senzory:**
   - Tepový pás nasaďte a navlhčete elektrody. Pás vysílá, jen když snímá tep.
   - Powermetr probudíte otočením klik.
3. Klikněte na **Hledat senzory** (15 s). Zobrazí se typ, ID a aktuální hodnota.
4. **Poznejte svoje zařízení:**
   - Hodnota v řádku se mění podle vás (šlapání, tep).
   - ID vysílače najdete i v hodinkách nebo cyklopočítači Garmin a ve Zwiftu, když v nich senzor párujete.
   - V bytovém domě můžete vidět i senzory sousedů.
5. Kliknutím vyberte své senzory (☑) a dejte **Spustit měření vybraných**. Výběr se uloží, příště stačí rovnou **Spustit měření**.

ANT+ vysílá všem přijímačům najednou, takže senzory můžou zároveň vysílat do hodinek nebo cyklopočítače. Exkluzivní je jen dongle: v PC ho může používat jen jeden program.

### Chytrý trenažér a souběh s Rouvy / Zwiftem
- **Výkon z trenažéru:** AntFan přečte výkon a kadenci i z chytrého trenažéru (ANT+ FE-C, třeba Decathlon). Trenažér jen poslouchá, odpor dál řídí Rouvy nebo Zwift. Když vyberete powermetr i trenažér, má přednost powermetr.
- **Souběh s Rouvy na jednom PC:** v Rouvy připojte trenažér a pás přes **Bluetooth**, AntFan pak dostane ANT+ dongle pro sebe. Většina trenažérů vysílá ANT+ i během připojení přes Bluetooth, u vašeho modelu to ověří testovací scénář. Druhá možnost je druhý ANT+ dongle jen pro AntFan.
- **Rouvy si dongle zabere, i když senzory páruje přes Bluetooth.** Když běží dřív než AntFan, AntFan senzory neuvidí a ukáže chybu „dongle drží ROUVY“. To je správně: AntFan mu dongle schválně nebere, aby se Rouvy nesekalo. Možnosti:
  1. **Druhý ANT+ dongle** (nejspolehlivější): AntFan si sám vezme ten volný. Nový dongle má stejné USB ID, takže pro něj ovladač libusbK nainstalujte stejně jako pro první.
  2. **Nejdřív AntFan, pak Rouvy:** spusťte AntFan a dejte „Spustit měření“. Teprve potom zapněte Rouvy a senzory v něm párujte jen přes Bluetooth.
- **Jeden dongle nemůžou používat dva programy najednou.** Pokud ho Rouvy i AntFan chtějí oba, jeden z nich prohraje a Rouvy se může sekat, protože se k donglu pořád pokouší připojit. Řešení jsou dvě. Buď v Rouvy párujte všechno jen přes Bluetooth, nebo kupte druhý ANT+ dongle. Se dvěma dongly si AntFan sám vezme ten volný.
- **AntFan je k Rouvy ohleduplný:**
  - Dongle, který používá jiný program, nikdy neresetuje.
  - Když dongle drží Rouvy, hned to oznámí a dál se nepokouší.
  - Za běhu neprochází USB zařízení.
  - Po ztrátě donglu nezatěžuje procesor.
  - Čtení z donglu má vysokou prioritu, takže se zprávy neztrácejí, ani když Rouvy vytěžuje počítač.
- **Tepový pás Polar:** ANT+ umí Polar H9. Polar H10 vysílá jen Bluetooth, takže ho AntFan přes ANT+ neuvidí.

## Řízení ventilátoru
Přepínač dole v okně: **Auto** řídí ventilátor podle pravidel, **Vyp/1/2/3** nastaví stupeň ručně. Všechno ostatní je v okně **Nastavení** a ukládá se hned. Tmavý motiv: **Nastavení → Vzhled** (Světlý / Tmavý / Podle systému).

### Řídit podle
| Režim | Chování |
|---|---|
| **Chytře: výkon zvyšuje, tep drží** (výchozí) | Výkon zvýší stupeň hned. Tep sám stupeň nezvýší, ale podrží dosažený stupeň, dokud neklesne. Tep reaguje na zátěž se zpožděním 30–60 s, takže ventilátor nezpomalí při krátkém odpočinku mezi intervaly. |
| Vyšší stupeň z výkonu a tepu | Platí ten vyšší z obou. |
| Jen výkon / Jen tep | Řídí jen jeden zdroj. |

Když jeden zdroj chybí (například nemáte powermetr), použije se automaticky ten druhý.

### Prahy (Nastavení → Řízení)
- **% FTP / % max. tepu** (výchozí): zadáte FTP a maximální tep a prahy jsou v procentech. Výchozí stupně jsou 30 / 60 / 85 % FTP a 55 / 70 / 82 % max. tepu. Vedle se ukáže přepočet na W a bpm. Když se zlepší forma, stačí změnit FTP.
- **W / bpm**: pevné hodnoty, výchozí 60 / 160 / 240 W a 105 / 135 / 155 bpm.
- **Hystereze**: stupeň se sníží, až když průměr klesne pod práh mínus tuto hodnotu (W, bpm).
- **Vyhlazení**: průměr za posledních N sekund. Výkon na kole hodně kolísá.

### Nastavení → Chování
- **Prodleva před snížením**: jak dlouho musí být hodnota nízko, než se stupeň sníží. Zvýšení je vždy okamžité.
- **Dofukování po tréninku**: po skončení šlapání ventilátor ještě N minut fouká na zvoleném stupni (výchozí 3 min na stupni 1) a pak se vypne. Hodnota 0 dofukování vypne.
- **Bez dat → stupeň**: co udělat, když po zadanou dobu nepřijdou žádná data (výchozí: vypnout). Dofukování má přednost.

Když přestanete šlapat, powermetr přestane posílat nové hodnoty. Program to po 3 s bere jako 0 W.
Každých 15 s program kontroluje skutečný stav ventilátoru. Když stupeň změníte ovladačem, v automatickém režimu ho program vrátí.

### Simulace
Zaškrtnutím **Simulace (bez hardwaru)** program vygeneruje falešné senzory a ventilátor. Hodí se k vyzkoušení pravidel.

Postup testování všech funkcí je v souboru [TESTOVANI.md](TESTOVANI.md).

## Řešení problémů

### „Dongle je připojen k jiné aplikaci“, i když žádná neběží
Program na to pamatuje několika způsoby:

- **Uvolnění po chybě:** knihovna openant po neúspěšném otevření nechá dongle otevřený ve vlastním procesu. Každý další pokus pak hlásí „obsazeno“. AntFan to opravuje a po chybě dongle vždy uvolní.
- **Opakované pokusy:** když otevření selže, zkusí to celkem 4× a mezitím provede USB reset donglu.
- **Jediná instance:** druhá kopie AntFan se nespustí. Pokud stará kopie visí na pozadí bez okna (typicky `pythonw.exe`), nabídne její ukončení.
- **Diagnostika:** když dongle opravdu drží jiný program, AntFan vypíše, který to je. Rozpozná například Zwift Launcher, Garmin Express, TrainerRoad, MyWhoosh a ROUVY.
- **Nastavení → Diagnostika → Resetovat dongle:** uvolní dongle a provede USB reset, stejně jako by se vytáhl a zapojil.
- **Vytažení za běhu:** měření se po zapojení obnoví samo.

Když nic z toho nepomůže, zapojte dongle do jiného USB portu (ne do hubu) a na Windows ve Správci zařízení zkontrolujte, že má ovladač libusbK.

### Výkon občas na chvíli spadne na 0 W
**Hlavní příčina nalezena a opravena:** knihovna openant otevírala kanály v režimu „background scanning“. Kanál se v něm na senzor nezachytí a zprávy chytá jen náhodou. Podle logu dorazilo při měření jen 7–11 % zpráv, zatímco při hledání senzorů ~90 %. AntFan teď otevírá normální sledovací kanály a příjem by měl být 90–100 %.

Od této verze AntFan bere výkon z **každé** přijaté zprávy (asi 4× za sekundu), ne jen ze zpráv, kde se změní čítač událostí. Na 0 W přepne, jen když zprávy chodí a čítač 3,5 s stojí, tedy když opravdu nešlapete. Když zprávy na chvíli nechodí vůbec (výpadek příjmu), drží poslední hodnotu až 12 s. U výkonu se pak ukáže „⚠ výpadek příjmu“.

Ve sloupci **Příjem** je vidět, kolik % zpráv od senzoru za posledních 5 s dorazilo. Pod 80 % se zbarví červeně.
- **Příjem pod ~90 %:** dejte dongle blíž ke kolu. Nejlépe na USB prodlužovačce na zem nebo na stolek k trenažéru, s přímou viditelností. Přední USB porty a USB 3.0 (modré) porty dost ruší, a stejně tak Wi-Fi router nebo ventilátor hned u donglu.
- **Trenažér vysílá výkon dvakrát**, jako *Powermetr* i jako *Trenažér* se stejným ID. Zkuste vybrat jen jeden z nich a porovnejte příjem a plynulost výkonu.
- **Kde je problém, napíše AntFan sám** pod seznamem senzorů:
  - **Výpadky na všech senzorech zároveň:** příčina je v PC. Zkuste jiný USB port (USB 2.0, ne hub), prodlužovačku nebo jiný dongle a dejte router nebo ventilátor dál od donglu.
  - **Vypadává jen jeden senzor:** příčina je u senzoru. Bývá to jeho Bluetooth spojení s Rouvy, protože senzor se rádiem dělí mezi Bluetooth a ANT+. Může to být i baterie nebo u pásu kontakt s kůží.
- **Pro diagnostiku** AntFan každých 5 s zapíše do `antfan.log` souhrn příjmu každého senzoru (počet zpráv, nejdelší mezera, změny čítače, výkon). Každý výpadek delší než 1,5 s zapíše zvlášť. Po jízdě pošlete log, z něj je přesně vidět, co se dělo.

### Ostatní
- **„ANT+ dongle nenalezen“**: zkontrolujte, že je dongle zapojený, a ve Správci zařízení ověřte ovladač (libusbK/WinUSB).
- **Ventilátor neodpovídá**: špatná IP, jiná síť nebo blokace firewallem.
- **„špatný token“**: token se změní při každém novém spárování ventilátoru, takže ho získejte znovu.
- Log: `%APPDATA%\AntFan\antfan.log`, nastavení: `%APPDATA%\AntFan\config.json`.

## Struktura
```
antfan/ant_backend.py   ANT+ vyhledávání (continuous scan) a měření tepu, powermetru a trenažéru (openant)
antfan/selftest.py      kontrola sestaveného exe (--selftest)
antfan/rx.py            příjem ze senzoru: dekódování výkonu, kvalita signálu, diagnostika do logu
antfan/usb_diag.py      diagnostika obsazeného donglu, USB reset, oprava úniku v openant
antfan/single_instance.py  jen jedna spuštěná instance
antfan/miio_fan.py      protokol miIO pro Xiaomi ventilátor (bez python-miio)
antfan/controller.py    výpočet stupně: chytrý režim, % FTP, vyhlazení, hystereze, dofukování
antfan/app.py           GUI (tkinter)
```
