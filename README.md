# AntFan – ventilátor řízený výkonem a tepem (ANT+)

Program pro Windows 11:

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
| **Ventilátor** | Xiaomi Smart Standing Fan 2 Lite (`dmaker.fan.1c`, odzkoušený), další Xiaomi ventilátory podle specifikace, obyčejný ventilátor přes Shelly, cokoli přes Home Assistant | jiné značky bez Home Assistant |
| **Počítač** | Windows 10 a 11 | macOS a Linux zatím ne |

Samostatné čidlo rychlosti a kadence AntFan nepoužívá, kadenci bere z powermetru nebo trenažéru.

**Ventilátory** podrobně viz [Připojení ventilátoru](#připojení-ventilátoru).

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

## Připojení ventilátoru

V **Nastavení → Ventilátor** vyberte typ:

| Typ | Co ovládá | Stupně |
|---|---|---|
| **Xiaomi** | ventilátory Xiaomi / Mijia / Smartmi / dmaker v domácí Wi-Fi (bez cloudu) | stupně nebo rychlost v % podle modelu |
| **Shelly zásuvka** | obyčejný ventilátor zapojený přes Shelly relé (Gen1 i Plus/Pro, bez hesla) | jen zapnout od zvoleného stupně |
| **Home Assistant** | jakoukoli entitu `fan.*` (rychlost v %) nebo `switch.*` | podle entity |

### Xiaomi
AntFan posílá příkazy ventilátoru **přímo v domácí síti** (UDP port 54321). Komunikace je šifrovaná **tokenem**, tajným klíčem, který ventilátor vytvoří při spárování s aplikací Mi Home. Aplikace Mi Home i dálkový ovladač fungují dál normálně.

1. **Spárujte ventilátor** v aplikaci Mi Home. Ventilátor umí jen Wi-Fi 2,4 GHz a PC musí být ve stejné síti (síť pro hosty zařízení často izoluje).
2. **Klikněte na „Získat z účtu Xiaomi…“.** AntFan ukáže QR kód, ten naskenujete v aplikaci Mi Home a přihlášení potvrdíte v telefonu. Heslo se nikam nezadává. Pak vyberte ventilátor ze seznamu a AntFan vyplní IP adresu i token sám.
   - Na stejném počítači můžete místo QR kódu kliknout na „Otevřít přihlášení v prohlížeči“.
   - Seznam zařízení se stáhne jen jednou při tomto kroku. Ovládání pak jde bez cloudu.
   - Když to nejde, token získáte i nástrojem [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) (z jeho protokolu vychází i AntFan) a vyplníte ho ručně.
3. **Nastavte pevnou IP:** v routeru ventilátoru zarezervujte IP adresu (DHCP rezervace podle MAC adresy).
4. **Vyzkoušet.** AntFan zjistí model a sám vybere správné ovládání:
   - **přímo podporované modely** (předvolby ze specifikací Xiaomi MIoT): `dmaker.fan.1c` (odzkoušený), `dmaker.fan.p5c/p8/p9/p10/p11/p15/p18/p28/p30/p33/p39/p42/p44/p45/p220/p221/p23/tn1/01/02/1e`, `xiaomi.fan.2lite/p23/p30/p43/p45/p51/p69/p70/p76/p85/p90`, `zhimi.fan.za5/fa1/fa2/fb1`, `leshow.fan.ss4/ss310/ss320`, `viomi.fan.v5–v8/v13`, `dreame.fan.*` a další,
   - **starší modely se starým protokolem**: `zhimi.fan.v2/v3/sa1/za1/za3/za4`, `dmaker.fan.p5`,
   - **ostatní modely**: AntFan si stáhne jejich specifikaci z <https://miot-spec.org> a uloží ji.
   Kromě `dmaker.fan.1c` jsou modely ověřené jen podle specifikace, ne na skutečném ventilátoru. Když u vás funguje jiný model, napište to do Issues.
5. **Počet stupňů** v AntFan (1–5) může být jiný než počet stupňů ventilátoru. AntFan je rozloží rovnoměrně: třeba 3 stupně AntFan na ventilátoru se 4 stupni = 1, 3, 4, a u rychlosti v % = 34 %, 67 %, 100 %.

Token se změní, když ventilátor resetujete nebo znovu spárujete. Pak ho získejte znovu.

### Shelly
Zadejte IP adresu Shelly, výstup (u jednokanálových 0) a od jakého stupně se má zapnout. Rychlost nastavte na ventilátoru, AntFan ho jen zapíná a vypíná. Shelly musí mít vypnuté heslo (AntFan heslo zatím neumí).

### Home Assistant
Zadejte adresu (třeba `http://homeassistant.local:8123`), dlouhodobý token (profil v Home Assistant → Zabezpečení → Dlouhodobé přístupové tokeny) a entitu, třeba `fan.vetrak` nebo `switch.zasuvka_vetrak`. Entita `fan.*` dostane rychlost v %, `switch.*` se zapne od zvoleného stupně.

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

Když nic z toho nepomůže, zapojte dongle do jiného USB portu (ne do hubu) a ve Správci zařízení zkontrolujte, že má ovladač libusbK.

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
