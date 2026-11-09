# AntFan – ventilátor řízený výkonem a tepem (ANT+ / Bluetooth)

[English](README.en.md)

**Pro koho to je:** pro každého, kdo jezdí doma na trenažéru (Rouvy, Zwift, MyWhoosh nebo jen tak) a nechce během jízdy slézat z kola kvůli ventilátoru. Když zaberete, začnete se potit a tep jde nahoru, AntFan ventilátor sám zesílí. Když povolíte nebo si dáte pauzu, zase ho ztlumí. Nic nemusíte mačkat.

**Co k tomu potřebujete:** počítač s Windows nebo Macem, tepový pás, powermetr nebo chytrý trenažér (ANT+ přes USB dongle, nebo Bluetooth) a ventilátor, který jde ovládat přes Wi-Fi: Xiaomi, obyčejný ventilátor v chytré zásuvce Shelly, nebo cokoli v Home Assistantu. Vyzkoušet se dá i bez čehokoli z toho v režimu **Simulace**.

Co program dělá:

1. připojí se k ANT+ USB donglu nebo k Bluetooth senzorům,
2. vyhledá tepové pásy, powermetry a chytré trenažéry (ANT+ FE-C, Bluetooth FTMS) v okolí,
3. zobrazuje výkon, kadenci a tep v reálném čase (s grafem za posledních 10 minut),
4. podle hodnot nastavuje rychlost ventilátoru přes domácí Wi-Fi.

Program je v češtině i angličtině (Nastavení → Vzhled → Jazyk).

## Podporovaná zařízení

| Zařízení | Funguje | Nefunguje |
|---|---|---|
| **ANT+ dongle** | Garmin ANT+ USB stick (ANTUSB2, `0fcf:1008`), Garmin mini stick (ANTUSB-m, `0fcf:1009`) a většina levných klonů (CooSpo, CYCPLUS, Anself…), které se hlásí stejně | starý stick první generace (`0fcf:1004`), Bluetooth |
| **Tepový pás** | jakýkoli s ANT+: Garmin HRM, Wahoo TICKR, Scosche Rhythm+, Garmin hodinky se zapnutým *vysíláním tepu*; přes Bluetooth i Polar H9, H10, Verity Sense (viz [Bluetooth senzory](#bluetooth-senzory)) | – |
| **Powermetr** | jakýkoli ANT+: pedály (Garmin Rally, Favero Assioma), kliky (Stages, 4iiii, Quarq); přes Bluetooth každý se službou Cycling Power | – |
| **Chytrý trenažér** | jakýkoli s ANT+ FE-C: Tacx, Wahoo KICKR, Elite, Zwift Hub…; přes Bluetooth každý s FTMS nebo Cycling Power | Bluetooth trenažér jen s vlastním protokolem (bez FTMS i Cycling Power) |
| **Ventilátor** | Xiaomi Smart Standing Fan 2 Lite (`dmaker.fan.1c`, odzkoušený), další Xiaomi ventilátory podle specifikace, obyčejný ventilátor přes Shelly, cokoli přes Home Assistant | jiné značky bez Home Assistant |
| **Počítač** | Windows 10 a 11, macOS 11+ na Macu s Apple Silicon (M1 a novější), viz [macOS](#macos) | Mac s procesorem Intel (sestavení je jen pro arm64), Linux zatím ne |

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

## macOS

Aplikace pro Mac s Apple Silicon (M1 a novější). Ovladač donglu se na Macu neinstaluje ani nemění, Zadig není potřeba.

1. V sekci [Releases](../../releases) stáhněte **`AntFan-macOS.zip`** a rozbalte ho (dvojklik).
2. **`AntFan.app`** přetáhněte do složky *Aplikace*.
3. **První spuštění:** aplikace není podepsaná u Applu, takže macOS při prvním otevření hlásí *„Soubor AntFan nebyl otevřen“*. Klikněte na **Hotovo** (ne *Přesunout do koše*) a pak:
   - otevřete **Nastavení systému → Soukromí a zabezpečení**, sjeďte dolů a u hlášky o AntFanu klikněte na **Přesto otevřít**, potvrďte heslem nebo Touch ID a AntFan spusťte znovu,
   - nebo v Terminálu odstraňte příznak stažení:
   ```bash
   xattr -dr com.apple.quarantine /Applications/AntFan.app
   ```
   Stačí jednou, další spuštění už jdou normálně. (Starší macOS umí i **pravé tlačítko → Otevřít**.)
4. Zapojte ANT+ dongle (na USB-C přes redukci) a spusťte měření.

Dongle může naráz používat jen jedna aplikace. Zwift, ROUVY, TrainerRoad, Garmin Express apod. musí dongle pustit, jinak AntFan hlásí, že je obsazený (a vypíše, který program běží). Garmin Express a Zwift Launcher běží na pozadí i po zavření okna, zkontrolujte ikonky v horní liště.

Nastavení a log jsou v `~/Library/Application Support/AntFan/` (Nastavení → Diagnostika → *Otevřít složku s logem*).

**Ze zdrojového kódu:** Python 3.10+ z <https://www.python.org/downloads/macos/> (obsahuje tkinter), pak v Terminálu ve složce projektu:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m antfan
```

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

### Najít moje senzory (chytré párování)
V bytovém domě je vidět víc pásů a powermetrů. **Nastavení → Senzory → Najít moje senzory** to rozhodne samo:
1. Spustí hledání (20 s) a vyzve vás: zašlapejte a navlhčete pás nebo se ho dotkněte.
2. Vaše senzory zareagují: výkon nebo kadence vyskočí z 0 a čítač otáček se hýbe, pás začne měřit nebo tep stoupne, Bluetooth senzor se probudí a objeví. Pomůže i síla signálu, vaše senzory bývají blíž.
3. Senzory, které nereagují, patří nejspíš sousedům. AntFan navrhne pás a výkon (powermetr má přednost před trenažérem, trenažér se stejným ID jako Trenažér i Powermetr vezme jednou). **Použít** výběr uloží.

Když nic nezareaguje, AntFan poradí, co zkusit. Senzory jde vždy vybrat i ručně kliknutím.

### Průvodce souběhem s Rouvy
Když běží Rouvy, Zwift, TrainerRoad, MyWhoosh a podobné (Windows i macOS), nebo když dongle drží jiný program, ukáže AntFan v okně jízdy nenápadný pruh s doporučením:
- **Dva dongly:** každý program má svůj, v obou párujte přes ANT+.
- **Dongle má Rouvy:** AntFan pojede přes Bluetooth. Tlačítko **Přepnout na Bluetooth senzory** vybere BT verze vašich senzorů (pozná je podle ID v názvu, třeba „Tacx Flux 61234“). V Rouvy pak párujte jen přes ANT+.
- **Dongle má AntFan:** v Rouvy párujte senzory přes Bluetooth.

Trenažér i pás obvykle dovolí jen 1–2 Bluetooth spojení naráz, proto stejný senzor nepřipojujte přes Bluetooth k oběma programům. Pruh se ukáže jednou za spuštění, jde zavřít. Podrobnosti a vypnutí: **Nastavení → Souběh**.

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
- **Tepový pás Polar:** ANT+ umí Polar H9. Polar H10 a Verity Sense vysílají jen Bluetooth, AntFan je najde jako „Tepový pás (BT)“.

## Bluetooth senzory
AntFan umí kromě ANT+ i senzory s Bluetooth (BLE). Dongle pro ně není potřeba, stačí Bluetooth v počítači.

| Senzor | Bluetooth služba | Co AntFan čte |
|---|---|---|
| Tepový pás (BT) | Heart Rate (0x180D) | tep |
| Powermetr (BT) | Cycling Power (0x1818) | výkon, kadence z otáček klik (když je powermetr posílá) |
| Trenažér (BT) | Fitness Machine / FTMS (0x1826) | výkon a kadence |

- **Hledat senzory** hledá ANT+ i Bluetooth najednou. Bluetooth senzory mají v seznamu **(BT)**. Když dongle není zapojený, hledá se jen Bluetooth. V systému (Windows Nastavení → Bluetooth) senzory párovat nemusíte.
- **Měření:** ANT+ senzory jdou přes dongle, BT senzory přes Bluetooth. Jdou kombinovat, třeba pás přes Bluetooth a powermetr přes ANT+. Chyba donglu Bluetooth nezastaví.
- **Spojení na jednoho:** Bluetooth senzor často dovolí jen 1–2 spojení najednou. Když je pás nebo trenažér přes Bluetooth připojený k Rouvy, AntFan ho nemusí vůbec najít, nebo se o něj budou přetahovat. Umí-li senzor i ANT+, připojte ho jedním programem přes ANT+ a druhým přes Bluetooth.
- **Ztráta spojení:** AntFan se k senzoru připojí znovu sám, stav je v Nastavení → Diagnostika.
- **Příjem (%):** u Bluetooth je orientační. Senzory posílají různě často (tep asi 1× za s, výkon 1–4× za s), AntFan odhaduje očekávanou frekvenci z toho, co chodí.
- **ID** u BT senzoru je číslo, které si AntFan odvodí z adresy zařízení. Adresy se pamatují v `ble_devices.json` vedle `config.json`.
- **Windows:** Windows 10 (1809) nebo 11 a adaptér Bluetooth 4.0 nebo novější.
- **macOS:** aplikace musí mít v `Info.plist` klíč `NSBluetoothAlwaysUsageDescription`, jinak ji macOS při prvním použití Bluetooth ukončí. AntFan to předem zkusí v samostatném procesu a místo pádu ukáže chybu. Při spuštění z Terminálu přes `python` tento klíč chybí, Bluetooth jde jen v sestavené AntFan.app. Přístup se povoluje v Nastavení systému → Soukromí a zabezpečení → Bluetooth.

### Baterie senzorů
Sloupec **Baterie** v Nastavení → Senzory ukazuje procenta (tepový pás, pokud je posílá) nebo stav nová / dobrá / OK / slabá / kritická. Slabá baterie je červeně a v okně jízdy u příjmu senzoru je „· slabá baterie“. Když baterie klesne pod hranici, ukáže se v okně jízdy jednou za spuštění pruh s upozorněním. Zapnutí a hranice (slabá / kritická, u senzorů s procenty pod 20 %) jsou v Nastavení → Senzory. Senzory posílají stav baterie zhruba jednou za minutu, údaj se proto objeví až chvíli po spuštění měření.

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

### Plynulá rychlost (Nastavení → Řízení → Výstup)
Místo stupňů roste rychlost lineárně: na 1. prahu **min. %** (výchozí 20 %), na posledním prahu 100 %, pod 1. prahem vypnuto. Platí pro všechny režimy (Chytře, Jen výkon…). Hystereze a prodleva zůstávají, rychlost pak klesá nejvýš o **Pokles nejvýš** %/s (výchozí 2 %/s). Dofukování i předstih fungují dál.

### Vítr podle rychlosti
Režim **Vítr podle rychlosti** foukne tak, jak rychle jedete. Rychlost posílá trenažér (FE-C, stránka 0x10), Rouvy ji tam promítá z virtuální trasy. Pod 5 km/h je vypnuto, pak rychlost ventilátoru roste lineárně do 100 % při **plné rychlosti** (výchozí 45 km/h). Volba **minimum podle výkonu a tepu** zabrání přehřátí při pomalém stoupání do kopce: platí vyšší z větru a chlazení podle výkonu.

Ventilátor s rychlostí v % (Xiaomi s plynulou rychlostí, Home Assistant `fan.*`) dostane % přímo, ostatní nejbližší stupeň. Změny pod 5 % se neposílají. V okně jízdy je ventilátor v % (u stupňových ventilátorů i se stupněm), v dlaždici je vidět například „vítr 32 km/h“.

### Nastavení → Chování
**Předstih** (výchozí vypnutý): když okamžitý výkon drží nad prahem vyššího stupně zadaný počet sekund (výchozí 3 s), stupeň naskočí hned, nečeká se na průměr. Krátký výkyv pod tu dobu nic nezmění a snižování zůstává pomalé.

- **Prodleva před snížením**: jak dlouho musí být hodnota nízko, než se stupeň sníží. Zvýšení je vždy okamžité.
- **Dofukování po tréninku**: po skončení šlapání ventilátor ještě N minut fouká na zvoleném stupni (výchozí 3 min na stupni 1) a pak se vypne. Hodnota 0 dofukování vypne.
- **Bez dat → stupeň**: co udělat, když po zadanou dobu nepřijdou žádná data (výchozí: vypnout). Dofukování má přednost.

Když přestanete šlapat, powermetr přestane posílat nové hodnoty. Program to po 3 s bere jako 0 W.
Každých 15 s program kontroluje skutečný stav ventilátoru. Když stupeň změníte ovladačem, v automatickém režimu ho program vrátí.

### Simulace
Zaškrtnutím **Simulace (bez hardwaru)** program vygeneruje falešné senzory a ventilátor. Hodí se k vyzkoušení pravidel.

Postup testování všech funkcí je v souboru [TESTOVANI.md](TESTOVANI.md).

## Ovládání z mobilu
Hodnoty (výkon, tep, stupeň) a přepínač **Auto | Vyp | 1–3** lze mít i na telefonu na řídítkách. Telefon musí být ve stejné Wi-Fi jako počítač, nic se neinstaluje.

1. V hlavním okně klikněte na **Zapnout mobil** (výchozí je vypnuto). Poprvé se otevře Nastavení → Mobil s QR kódem. Po zavření programu se ovládání z mobilu zase vypne. Kdo ho chce mít pořád, zaškrtne v Nastavení → Mobil **Zapnout hned po spuštění programu**.
2. Načtěte v telefonu QR kód, nebo otevřete adresu ve tvaru `http://<IP počítače>:8686/m/<klíč>`.
3. Windows se napoprvé zeptá, zda AntFan smí do sítě. Povolte **soukromé sítě**, jinak se telefon nepřipojí. Na macOS musí mít AntFan zapnutý přístup v **Nastavení systému → Soukromí a zabezpečení → Místní síť**.

- Adresa obsahuje náhodný klíč. Bez něj server odpoví 404. Kdo adresu zná, může ventilátor ovládat. Tlačítko **Nový klíč** starou adresu zneplatní.
- Port (výchozí 8686) jde změnit, když je obsazený.
- Stránka se obnovuje každou sekundu a řídí se tmavým režimem telefonu. Obrazovku telefonu nechte rozsvícenou.
- **Na počítači stránka jde, na telefonu ne** („Tento web není dostupný“, „ERR_TOO_MANY_RETRIES“, načítá se donekonečna):
  - IP adresa telefonu (Android: Nastavení → Wi-Fi → ozubené kolečko u sítě, iPhone: Nastavení → Wi-Fi → ⓘ) musí začínat stejně jako adresa počítače, např. obě `192.168.1.…`. Jinak je telefon v jiné síti nebo na mobilních datech.
  - Vypněte na telefonu **VPN** a aplikace, které se jako VPN chovají (blokátory reklam jako AdGuard, Blokada, NextDNS, Cloudflare WARP / 1.1.1.1, antiviry, na Samsungu *Zabezpečená Wi-Fi*). Posílají provoz mimo domácí síť, takže se k počítači nedostane.
  - Sítě pro hosty, firemní a školní Wi-Fi často zakazují, aby se zařízení viděla navzájem. Tam to bez změny nastavení routeru nepůjde.
  - Po **Novém klíči** naskenujte nový QR kód, stará adresa vrací „Not found“.
- Pro vlastní skripty: `GET /m/<klíč>/api/state` vrací JSON, `POST /m/<klíč>/api/level` s tělem `{"level": "auto"}` nebo `{"level": 2}` přepne stupeň.

## Připomínka pití
Volitelná, **výchozí je vypnuto**. Zapíná se v Nastavení → Pití. Během jízdy se pod grafem občas objeví tenký pruh „Napijte se · zhruba 150 ml“. Zmizí kliknutím nebo po minutě. Na mobilu se ukáže stejný pruh.

- Počítá jen během měření a když šlapete (výkon nebo kadence nad 0, bez powermetru podle tepu).
- Základ: každých 15 min, zhruba 500 ml za hodinu. Při vyšším výkonu (kJ za hodinu) až 750 ml/h a interval až 10 min. Nad 22 °C v místnosti víc a častěji. Po hodině jízdy je interval o 10 % kratší.
- **Teplota v místnosti** (výchozí 20 °C): prázdné pole = teplotu nepočítat. **Interval** v minutách: prázdné = automaticky.
- Hodnoty jsou jen orientační, nejde o zdravotní doporučení.

## Lišta navrchu
Malý tmavý proužek, který zůstává nad Rouvy a jinými aplikacemi. **Výchozí je vypnuto.** Zapíná se přepínačem „Lišta“ v horní liště okna jízdy nebo v Nastavení → Vzhled.

- Ukazuje jen to, co Rouvy neví: stupeň ventilátoru a za ním důvod („2 · výkon“, „1 · dofukování 1:40“, „ručně 2“). Volitelně druhé číslo: % max. tepu (výchozí), tepová zóna nebo nic.
- Upozornění jen když jsou: připomínka pití, slabá baterie senzoru, výpadek příjmu, ventilátor neodpovídá.
- Kliknutím na stupeň přepnete Auto → 1 → 2 → … → Vyp. Přetažením myší lištu posunete, pozice se uloží. Tlačítko „Vrátit lištu do rohu“ ji vrátí doprava nahoru.
- Velikost Mini nebo Standard. Režim **Jen upozornění**: lišta je skrytá a ukáže se na 20 s, když přijde upozornění.
- **Rouvy musí běžet v okně bez rámečku** (borderless / okno na celou obrazovku), ne v exkluzivní celé obrazovce. Přes exkluzivní režim se žádné okno nedostane.
- macOS: lišta je nad ostatními okny, ale ne nad aplikací v celoobrazovkovém prostoru (zelené tlačítko). Rouvy tam pusťte v maximalizovaném okně.
## Profily
Každý profil má vlastní řízení: FTP, max. tep, prahy, režim řízení a chování. Hodí se pro víc jezdců na jednom trenažéru nebo pro různé tréninky (například Vytrvalost a Intervaly).

- **Přepnutí:** kliknutím na „Profil: …“ v horní liště okna jízdy, nebo v **Nastavení → Řízení** nahoře. Přepnout jde i za jízdy, nové prahy platí hned.
- **Nový** zkopíruje aktuální profil, **Přejmenovat** změní jméno, **Smazat** smaže aktuální profil (poslední smazat nejde).
- Nastavení ze starší verze se při prvním spuštění převede na profil **Výchozí**.

## Shrnutí po jízdě
Během měření program 1× za sekundu zaznamenává výkon (okamžitý i vyhlazený), kadenci, tep a stupeň ventilátoru. Po **Zastavit**, nebo když po skončení šlapání doběhne dofukování, ukáže okno **Shrnutí jízdy**. Jen když jízda trvala aspoň 5 minut a byl výkon nebo tep.

- **Čísla:** délka, průměrný a max. výkon, NP (normalizovaný výkon), IF a TSS podle FTP profilu, práce v kJ, průměrný a max. tep, průměrná kadence.
- **Čas v zónách:** výkon v 7 zónách podle FTP (Coggan), tep v 5 zónách podle % max. tepu, čas na jednotlivých stupních ventilátoru.
- **Posun tepu:** o kolik % se ve druhé polovině jízdy zhoršil poměr výkon/tep proti první. Pod 5 % je dobré. Vyšší hodnota znamená, že tep při stejném výkonu stoupal (únava, teplo, málo pití).
- **Soubory:** každá jízda se uloží jako CSV do `%APPDATA%\AntFan\jizdy\RRRR-MM-DD_HHMM.csv` (oddělovač středník, otevře se v Excelu). Konec po dofukování, kdy se už nešlapalo, se odřízne. Rozjetá jízda se uloží i při zavření programu.
- **Starší jízdy:** **Nastavení → Jízdy** ukáže seznam posledních jízd. Dvojklikem otevřete jejich shrnutí.

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
- **Kde se zprávy ztratily, pozná AntFan z hlášení donglu.** Dongle u každé zprávy, kterou od senzoru čekal a nedostal, pošle hlášení „zmeškaná zpráva“. Když ztratí spojení se senzorem, ohlásí i to. U každého výpadku je pak v logu příčina:
  - *dongle zprávy čekal, ale od senzoru nepřišly*: rádio (senzor, dosah, rušení, Bluetooth spojení senzoru s Rouvy),
  - *dongle ztratil spojení se senzorem*: senzor nevysílal nebo nebyl slyšet,
  - *dongle zmeškané zprávy nehlásil*: senzor vysílal, ale zprávy se ztratily cestou do programu (USB port, ovladač, vytížený počítač). Takový výpadek se v aplikaci počítá jako problém na straně PC.
- **Pro diagnostiku** AntFan každých 5 s zapíše do `antfan.log` souhrn příjmu každého senzoru (počet zpráv, nejdelší mezera, změny čítače, výkon). Každý výpadek delší než 1,5 s zapíše zvlášť. Po jízdě pošlete log, z něj je přesně vidět, co se dělo.

### Rouvy (nebo jiná hra) se s AntFanem seká
AntFan sám procesor skoro nezatěžuje (ve Správci úloh má během jízdy ~0 % CPU). Když se přesto s ním seká obraz nebo celý počítač, bývá příčina v USB nebo ovladačích. Postupně zkuste:

1. **Spustit AntFan bez měření** (dongle se neotevře) a pak Rouvy. Když se nic neseká, vadí čtení z donglu přes USB, pokračujte bodem 2. Když se to seká i tak, vypněte **lištu navrchu** a mobil.
2. **Dongle do jiného USB portu**: vzadu přímo na desce, USB 2.0 (černý, ne modrý), ne do hubu, ideálně na prodlužovačce dál od počítače a od Bluetooth adaptéru.
3. **LatencyMon** (zdarma, Resplendence) během jízdy ukáže, který ovladač systém brzdí.

Rouvy přes Bluetooth a AntFan přes ANT+ jsou obě na 2,4 GHz. Dongle na prodlužovačce blíž ke kolu pomáhá oběma.

### Ostatní
- **„ANT+ dongle nenalezen“**: zkontrolujte, že je dongle zapojený, a ve Správci zařízení ověřte ovladač (libusbK/WinUSB).
- **Ventilátor neodpovídá**: špatná IP, jiná síť nebo blokace firewallem.
- **„špatný token“**: token se změní při každém novém spárování ventilátoru, takže ho získejte znovu.
- Log: `%APPDATA%\AntFan\antfan.log`, nastavení: `%APPDATA%\AntFan\config.json` (macOS: `~/Library/Application Support/AntFan/`). Log stačí najít tak, že do adresního řádku Průzkumníka zadáte `%APPDATA%\AntFan`.

## Struktura
```
antfan/ant_backend.py   ANT+ vyhledávání (continuous scan) a měření tepu, powermetru a trenažéru (openant)
antfan/ble_backend.py   Bluetooth senzory (bleak) a kombinovaný backend ANT+ a Bluetooth
antfan/pairing.py       chytré párování: které senzory zareagovaly (bez GUI)
antfan/coexist.py       průvodce souběhem s Rouvy/Zwiftem: detekce aplikací a doporučení
antfan/pairing_ui.py    GUI párování a průvodce (mixin pro App)
antfan/selftest.py      kontrola sestaveného exe (--selftest)
antfan/rx.py            příjem ze senzoru: dekódování výkonu, kvalita signálu, diagnostika do logu
antfan/battery.py       stav baterie (stránka 0x52, u tepového pásu stránka 7)
antfan/battery_ui.py    baterie v GUI: sloupec, upozornění v okně jízdy, volby
antfan/usb_diag.py      diagnostika obsazeného donglu, USB reset, oprava úniku v openant
antfan/single_instance.py  jen jedna spuštěná instance
antfan/miio_fan.py      protokol miIO pro Xiaomi ventilátor (bez python-miio)
antfan/controller.py    výpočet stupně: chytrý režim, % FTP, vyhlazení, hystereze, dofukování
antfan/vitr.py          plynulá rychlost a vítr podle rychlosti: mapování na %, pomalé snižování
antfan/vitr_ui.py       nastavení a dlaždice ventilátoru pro výstup v %
antfan/web.py           ovládání z mobilu: HTTP server a stránka pro telefon
antfan/drink.py         připomínka pití: interval a množství podle délky jízdy, výkonu a teploty
antfan/overlay.py       lišta navrchu přes Rouvy: stav z aplikace, okno bez rámečku, volby
antfan/qr.py            QR kód s adresou pro mobil (bez knihoven)
antfan/profiles.py      profily jezdců (každý má vlastní řízení)
antfan/ride.py          záznam jízdy, NP/IF/TSS, zóny, posun tepu, CSV
antfan/ride_ui.py       okno Shrnutí jízdy a stránka Jízdy
tests/                  unit testy: python -m unittest discover tests
antfan/app.py           GUI (tkinter)
tests/                  testy (python -m unittest discover tests)
```
