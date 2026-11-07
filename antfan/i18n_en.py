"""Anglický slovník: český text (klíč) -> anglický text. Viz i18n.py."""

EN = {
    # --- ant_backend
    "Tepový pás": "HR strap",
    "Powermetr": "Power meter",
    "Trenažér": "Trainer",
    "ANT+ dongle nenalezen. Je zapojený? Má ovladač libusbK nebo WinUSB (viz README)?":
        "ANT+ dongle not found. Is it plugged in? Does it have the libusbK or WinUSB driver (see README)?",
    "Chybí knihovna libusb (pip install libusb-package).": "The libusb library is missing (pip install libusb-package).",
    "ANT+ dongle nenalezen. Je zapojený? Zkuste jiný USB port nebo redukci.":
        "ANT+ dongle not found. Is it plugged in? Try another USB port or adapter.",
    "Resetuji dongle…": "Resetting dongle…",
    "[SIMULACE] Zastaveno": "[SIMULATION] Stopped",
    "[SIMULACE] Dongle resetován": "[SIMULATION] Dongle reset",
    "Dongle byl odpojen – zapojte ho znovu, měření se obnoví samo":
        "Dongle unplugged – plug it back in and measuring resumes automatically",
    "Nevybrán žádný senzor": "No sensor selected",
    "[SIMULACE] Měřím: ": "[SIMULATION] Measuring: ",
    "typ {device_type}": "type {device_type}",
    "Připojuji ANT+ dongle…": "Connecting ANT+ dongle…",
    "Vyhledávám senzory ({v} s)…": "Scanning for sensors ({v} s)…",
    "Vyhledávání dokončeno – nalezeno {v} senzorů": "Scan complete – {v} found",
    "Měřím: {names}": "Measuring: {names}",
    "[SIMULACE] Vyhledávám senzory ({v} s)…": "[SIMULATION] Scanning for sensors ({v} s)…",
    "Zastaveno": "Stopped",
    "Dongle je znovu zapojený, obnovuji měření…": "Dongle is back, resuming…",
    "Dongle nejde otevřít, zkouším znovu ({attempt}/{attempts})…":
        "Cannot open the dongle, retrying ({attempt}/{attempts})…",
    "[SIMULACE] Vyhledávání dokončeno – nalezeno {v} senzorů": "[SIMULATION] Scan complete – {v} found",
    "Spojení s ANT+ donglem se přerušilo a dongle teď nejde otevřít.\n\n":
        "The connection to the ANT+ dongle was lost and the dongle cannot be opened now.\n\n",

    # --- app: konstanty
    "Shelly zásuvka": "Shelly plug",
    "Světlý": "Light",
    "Tmavý": "Dark",
    "Podle systému": "System",
    "Chytře": "Smart",
    "Výkon zvyšuje, tep drží": "Power raises, HR holds",
    "Jen výkon": "Power only",
    "Reaguje hned": "Reacts instantly",
    "Jen tep": "HR only",
    "Bez powermetru": "No power meter",
    "Vyšší z obou": "Higher of both",
    "Fouká víc": "Blows more",
    "Vítr podle rychlosti": "Wind by speed",
    "Rychlost jízdy z trenažéru": "Ride speed from the trainer",
    "senzor": "sensor",
    "senzory": "sensors",
    "senzorů": "sensors",

    # --- app: jízda
    "Připraveno": "Ready",
    "nepřipojeno": "not connected",
    "Výkon · průměr": "Power · average",
    "Tep": "HR",
    "Ventilátor": "Fan",
    "Nastavení": "Settings",
    "Lišta": "Bar",
    "Zapnout mobil": "Phone on",
    "Vypnout mobil": "Phone off",
    "Spustit měření": "Start",
    "Zastavit": "Stop",
    "výkon, W": "power, W",
    "tep, bpm (60–200)": "HR, bpm (60–200)",
    "ventilátor": "fan",
    "posledních 10 min": "last 10 min",
    "Vyp": "Off",
    "vyp": "off",

    # --- app: nastavení
    "AntFan – nastavení": "AntFan – settings",
    "Senzory": "Sensors",
    "Řízení": "Control",
    "Chování": "Behavior",
    "Pití": "Drinking",
    "Vzhled": "Appearance",
    "Mobil": "Phone",
    "Jízdy": "Rides",
    "Souběh": "Other apps",
    "Diagnostika": "Diagnostics",
    "Kliknutím vyberte tepový pás a trenažér nebo powermetr. Výběr se pamatuje, příště stačí Spustit měření.":
        "Click to select your HR strap and trainer or power meter. The selection is remembered, next time just press Start.",
    "Hledat senzory": "Scan for sensors",
    "Najít moje senzory": "Find my sensors",
    "Typ": "Type",
    "Hodnota": "Value",
    "Příjem": "Signal",
    "Baterie": "Battery",
    "Najednou nejvýš {MAX_CHANNELS} senzorů. Trenažér vysílá výkon jako Trenažér i jako Powermetr se stejným ID, stačí vybrat jeden.":
        "Up to {MAX_CHANNELS} sensors at once. A trainer broadcasts power both as Trainer and as Power meter with the same ID, select just one.",
    "Najednou nejvýš {MAX_CHANNELS} senzorů.": "Up to {MAX_CHANNELS} sensors at once.",
    "Senzory (BT) jdou přes Bluetooth. Bluetooth senzor často dovolí jen 1–2 spojení najednou, s Rouvy na Bluetooth se mohou přetahovat. Umí-li senzor i ANT+, připojte ho jedním z programů přes ANT+.":
        "Sensors marked (BT) connect over Bluetooth. A Bluetooth sensor often allows only 1–2 connections at a time and may fight with Rouvy over Bluetooth. If the sensor also has ANT+, connect one of the apps over ANT+.",
    "Co AntFan ovládá. Údaje zůstávají jen v tomto počítači.":
        "What AntFan controls. The details stay on this computer only.",
    "IP adresa": "IP address",
    "IP adresa Shelly": "Shelly IP address",
    "Výstup (kanál)": "Output (channel)",
    "Zapnout od stupně": "Switch on from level",
    "Adresa": "Address",
    "Entita": "Entity",
    "Získat z účtu Xiaomi…": "Get from Xiaomi account…",
    "Přihlásíte se QR kódem v aplikaci Mi Home, heslo se nikam nezadává.":
        "You sign in with a QR code in the Mi Home app, no password is entered.",
    "Model se zjistí při připojení.": "The model is detected on connect.",
    "Vypnout pípání": "Mute beeps",
    "Vypnout podsvícení": "Turn off display light",
    "Obyčejný ventilátor v zásuvce Shelly umí jen zapnout a vypnout. Rychlost nastavte na ventilátoru. Shelly musí být bez hesla.":
        "A plain fan on a Shelly plug can only be switched on and off. Set the speed on the fan. The Shelly must have no password.",
    "Token: v Home Assistant profil → Zabezpečení → Dlouhodobé přístupové tokeny. Entita fan.* dostane rychlost v %, switch.* jen zapnout/vypnout od zadaného stupně.":
        "Token: in Home Assistant go to Profile → Security → Long-lived access tokens. A fan.* entity gets speed in %, a switch.* entity is only switched on/off from the given level.",
    "Počet stupňů": "Number of levels",
    "Uložit a připojit": "Save and connect",
    "Vyzkoušet": "Test",
    "Podle čeho a od jakých hodnot ventilátor přidává.": "What drives the fan and at which values it steps up.",
    "Řídit podle": "Control by",
    "Max. tep": "Max HR",
    "Prahy v": "Thresholds in",
    "% FTP a % max. tepu": "% FTP and % max HR",
    "W a bpm": "W and bpm",
    "Stupeň": "Level",
    "Výkon": "Power",
    "Změny se ukládají hned. Hystereze, vyhlazení a dofukování jsou v Chování.":
        "Changes are saved immediately. Hysteresis, smoothing and cooldown are under Behavior.",
    "Jak rychle ventilátor reaguje a co dělá po tréninku.": "How fast the fan reacts and what it does after the workout.",
    "Hystereze výkonu": "Power hysteresis",
    "Hystereze tepu": "HR hysteresis",
    "Vyhlazení výkonu": "Power smoothing",
    "Vyhlazení tepu": "HR smoothing",
    "Prodleva před snížením": "Delay before stepping down",
    "Dofukování po tréninku": "Cooldown after workout",
    "…na stupni": "…at level",
    "Bez dat ze senzorů stupeň": "Level with no sensor data",
    "…po": "…after",
    "Předstih: výkon nad prahem": "Lead: power above threshold",
    "Předstih: při nástupu výkonu zvýšit stupeň hned": "Lead: step up immediately when power surges",
    "Hystereze: stupeň klesne, až hodnota spadne o tolik pod práh. Prodleva: jak dlouho musí být pod prahem. Chytrý režim navíc drží stupeň podle tepu, takže ventilátor nezpomalí v krátkém odpočinku mezi intervaly. Předstih: když okamžitý výkon drží nad prahem vyššího stupně zadaný počet sekund, stupeň naskočí hned, ne až po průměru.":
        "Hysteresis: the level drops once the value falls this far below the threshold. Delay: how long it must stay below. Smart mode also holds the level by HR, so the fan does not slow down during short rests between intervals. Lead: when instant power stays above the next level's threshold for the given seconds, the level steps up right away instead of waiting for the average.",
    "Tmavý motiv méně oslňuje při jízdě v šeru.": "The dark theme is easier on the eyes when riding in dim light.",
    "Podle systému: řídí se nastavením ": "System: follows the setting in ",
    "macOS (Nastavení systému → Vzhled).": "macOS (System Settings → Appearance).",
    "Windows (Přizpůsobení → Barvy).": "Windows (Personalization → Colors).",
    "Jazyk": "Language",
    "Hodnoty a přepínač stupně na telefonu ve stejné Wi-Fi. Stačí otevřít adresu v prohlížeči, nic se neinstaluje.":
        "Values and the level switch on a phone on the same Wi-Fi. Just open the address in a browser, nothing to install.",
    "Zapnuto": "On",
    "Zapnout hned po spuštění programu": "Turn on when the app starts",
    "Jinak se zapíná tlačítkem Zapnout mobil v hlavním okně a po zavření programu se vypne.":
        "Otherwise it is turned on with the Phone on button in the main window and turns off when the app closes.",
    "Zkopírovat adresu": "Copy address",
    "Nový klíč": "New key",
    "Kdo zná adresu, může ventilátor ovládat. Nový klíč starou adresu zneplatní.":
        "Anyone who knows the address can control the fan. A new key invalidates the old address.",
    "Windows se při prvním zapnutí zeptá, zda AntFan smí do sítě. Povolte soukromé sítě, jinak se telefon nepřipojí.":
        "On first use Windows asks whether AntFan may access the network. Allow private networks, otherwise the phone cannot connect.",
    "Když něco nefunguje.": "When something does not work.",
    "Stav donglu": "Dongle status",
    "Resetovat dongle": "Reset dongle",
    "Uvolní dongle a provede USB reset, jako byste ho vytáhli a znovu zapojili.":
        "Releases the dongle and performs a USB reset, as if you unplugged it and plugged it back in.",
    "Příjem senzorů": "Sensor signal",
    "Otevřít složku s logem": "Open log folder",
    "Soubor antfan.log pošlete, když chcete poradit s problémem. Token v něm není.":
        "Send the antfan.log file when you need help with a problem. It does not contain your token.",
    "Simulace (bez donglu a ventilátoru)": "Simulation (no dongle or fan)",

    # --- app: hlášky
    "Prahy musí stoupat: stupeň 1 < 2 < 3.": "Thresholds must increase: level 1 < 2 < 3.",
    "Prahy musí být kladné.": "Thresholds must be positive.",
    "Výkon nejvýš 200 % FTP, tep nejvýš 100 % max. tepu.": "Power at most 200 % FTP, HR at most 100 % max HR.",
    "Zadejte čísla.": "Enter numbers.",
    "Neuloženo: {msg}": "Not saved: {msg}",
    "Neuloženo: {e}": "Not saved: {e}",
    "Neuloženo: Zadejte čísla.": "Not saved: Enter numbers.",
    "Zadejte IP adresu a token ventilátoru, nebo je získejte z účtu Xiaomi.":
        "Enter the fan's IP address and token, or get them from your Xiaomi account.",
    "simulovaný ventilátor": "simulated fan",
    "připojuji…": "connecting…",
    "Nejdřív vyhledejte senzory a kliknutím vyberte tepový pás a trenažér nebo powermetr.":
        "First scan for sensors and click to select your HR strap and trainer or power meter.",
    "Log je ve složce:\n{d}\n\n({e})": "The log is in this folder:\n{d}\n\n({e})",
    "Počet stupňů se projeví po restartu programu.": "The number of levels takes effect after restarting the app.",
    "Simulace: OK": "Simulation: OK",
    "Ventilátor odpovídá: {v} (firmware {v2}), {v3}, stupeň {v4}.": "Fan responds: {v} (firmware {v2}), {v3}, level {v4}.",
    "zapnutý": "on",
    "vypnutý": "off",
    " Ovládání: {note}.": " Control: {note}.",
    "Zkouším spojení…": "Testing connection…",
    "Port {web_port} nejde použít (obsazený?). Zvolte jiný.": "Port {web_port} cannot be used (in use?). Choose another.",
    "Mobil zapnutý": "Phone on",
    "Mobil: chyba": "Phone: error",
    "Běží na portu {port}. Otevřete adresu v telefonu nebo načtěte QR kód.":
        "Running on port {port}. Open the address on your phone or scan the QR code.",
    "Vypnuto.": "Off.",
    "Port musí být číslo 1024–65535.": "Port must be a number 1024–65535.",
    "Nejdřív ovládání z mobilu povolte.": "Turn on phone control first.",
    "Adresa zkopírována.": "Address copied.",
    "Ventilátor nepřipojen. ": "Fan not connected. ",
    "Slabá baterie": "Low battery",
    "Nenápadná připomínka pod grafem během jízdy. Interval a množství se řídí délkou jízdy, výkonem a teplotou v místnosti.":
        "A subtle reminder below the chart while riding. Interval and amount depend on ride time, power and room temperature.",
    "Připomínat pití": "Remind me to drink",
    "Teplota v místnosti": "Room temperature",
    "°C, prázdné = nepočítat": "°C, empty = ignore",
    "Interval": "Interval",
    "min, prázdné = automaticky": "min, empty = automatic",
    "Počítá jen během měření, když šlapete. Základ je zhruba 500 ml za hodinu, při vyšším výkonu až 750 ml, nad 22 °C víc. Jen orientační hodnoty, řiďte se i žízní. Připomínka zmizí kliknutím nebo po minutě.":
        "Counts only while measuring and pedaling. The base is about 500 ml per hour, up to 750 ml at higher power, more above 22 °C. Rough values only, listen to your thirst too. The reminder disappears on click or after a minute.",
    "Teď: ": "Now: ",
    "Vyhledávání": "Scan",
    " · slabá baterie": " · low battery",
    "Výpadky na všech senzorech zároveň ({all_n}× za 5 min). Příčina je v PC: zkuste jiný USB port (USB 2.0, ne hub), prodlužovačku nebo jiný dongle.":
        "Dropouts on all sensors at once ({all_n}× in 5 min). The cause is on the PC side: try another USB port (USB 2.0, not a hub), an extension cable or another dongle.",
    "Vypadává jen {who} za 5 min, ostatní senzory jdou. Příčina je u senzoru: Bluetooth spojení s Rouvy, baterie, kontakt pásu.":
        "Only {who} drops out (last 5 min), other sensors are fine. The cause is the sensor: Bluetooth connection to Rouvy, battery, strap contact.",
    "Slabý příjem: ": "Weak signal: ",
    ". Dejte dongle blíž ke kolu.": ". Move the dongle closer to the bike.",
    "Bez výpadků za posledních 5 minut.": "No dropouts in the last 5 minutes.",
    "Měření neběží.": "Not measuring.",
    "Měřím · {n} {v}": "Measuring · {n} {v}",
    "Hledám senzory…": "Scanning for sensors…",
    "Dongle odpojen": "Dongle unplugged",
    "Chyba ANT+": "ANT+ error",
    "Simulace": "Simulation",
    "ručně": "manual",
    "čeká na měření": "waiting for start",
    "předstih": "lead",
    "výkon": "power",
    "tep": "HR",
    "předstih · výkon nad {v} W": "lead · power above {v} W",
    "výkon nad prahem {v} W": "power above {v} W",
    "výkon pod prahem {v} W": "power below {v} W",
    "tep nad prahem {v} bpm": "HR above {v} bpm",
    "tep pod prahem {v} bpm": "HR below {v} bpm",
    "Výkon · průměr {power_smoothing_s:g} s": "Power · {power_smoothing_s:g} s avg",
    "výpadek příjmu {power_gap_s:.0f} s": "signal lost {power_gap_s:.0f} s",
    " · ventilátor zatím na {v}": " · fan still at {v}",
    "Simulovaný ventilátor": "Simulated fan",
    "Ventilátor připojen": "Fan connected",
    "Ventilátor nepřipojen": "Fan not connected",
    "Uvolňuji dongle…": "Releasing dongle…",
    "AntFan už běží": "AntFan is already running",
    "AntFan už běží. Pokud jeho okno nevidíte, ukončete ho {v} a spusťte program znovu.":
        "AntFan is already running. If you cannot see its window, end it {v} and start the app again.",
    "AntFan už běží (PID {pid}). Pokud jeho okno nevidíte, nejspíš visí na pozadí a drží ANT+ dongle – proto pak dongle hlásí, že je připojen k jiné aplikaci.\n\nUkončit starou instanci a pokračovat?":
        "AntFan is already running (PID {pid}). If you cannot see its window, it is probably stuck in the background holding the ANT+ dongle – that is why the dongle reports being used by another app.\n\nEnd the old instance and continue?",
    "Starou instanci se nepodařilo ukončit. Zkuste {v}.": "Could not end the old instance. Try {v}.",

    # --- battery
    "nová": "new",
    "dobrá": "good",
    "slabá": "low",
    "kritická": "critical",
    ". Vyměňte ji nebo nabijte před další jízdou.": ". Replace or charge it before the next ride.",
    "Slabá baterie: ": "Low battery: ",
    "Skrýt": "Hide",
    "Upozornit na slabou baterii": "Warn about low battery",
    "Hranice:": "Threshold:",
    "nebo pod": "or below",
    "% u senzorů, které posílají procenta": "% for sensors that report percent",

    # --- ble_backend
    "Bluetooth: program nemá oprávnění (macOS: Nastavení → Soukromí → Bluetooth).":
        "Bluetooth: the app has no permission (macOS: Settings → Privacy → Bluetooth).",
    "Bluetooth je vypnutý.": "Bluetooth is off.",
    "Bluetooth adaptér nenalezen.": "No Bluetooth adapter found.",
    "Bluetooth: macOS AntFanu nepovolil přístup. Povolte ho v Nastavení systému → Soukromí a zabezpečení → Bluetooth.":
        "Bluetooth: macOS denied AntFan access. Allow it in System Settings → Privacy & Security → Bluetooth.",
    "Bluetooth zastaven": "Bluetooth stopped",
    "Bluetooth: macOS program nepustil k Bluetooth (chybí oprávnění). Spusťte AntFan jako aplikaci AntFan.app a povolte Bluetooth v Nastavení systému → Soukromí a zabezpečení → Bluetooth.":
        "Bluetooth: macOS blocked access to Bluetooth (no permission). Run AntFan as the AntFan.app application and allow Bluetooth in System Settings → Privacy & Security → Bluetooth.",
    "{pre}Vyhledávání dokončeno – nalezeno {n} senzorů": "{pre}Scan complete – {n} found",
    "Bluetooth: kontrola oprávnění selhala ({name__}).": "Bluetooth: permission check failed ({name__}).",
    "ANT+ dongle nezapojen": "ANT+ dongle not plugged in",
    "Bluetooth: vyhledávání dokončeno – nalezeno {v} senzorů": "Bluetooth: scan complete – {v} found",
    "senzor nevysílá (vypnutý, mimo dosah, nebo už je připojený k jinému programu)":
        "sensor not broadcasting (off, out of range, or already connected to another app)",
    "{pre}Vyhledávám senzory {what} ({v} s)…": "{pre}Scanning for sensors {what} ({v} s)…",
    "{pre}Zastaveno": "{pre}Stopped",
    "Bluetooth: {type_name} #{device_id} neznám adresu – vyhledejte senzory znovu":
        "Bluetooth: {type_name} #{device_id} address unknown – scan for sensors again",
    "{label} hledám…": "{label} searching…",
    "{label} připojuji…": "{label} connecting…",
    "{label} připojen": "{label} connected",
    "Bluetooth: hledám ({v} s)…": "Bluetooth: scanning ({v} s)…",
    "{label} spojení ztraceno, připojuji znovu…": "{label} connection lost, reconnecting…",
    "{type_name} #{device_id} připojen": "{type_name} #{device_id} connected",

    # --- coexist
    "Trenažér i pás obvykle dovolí jen 1–2 Bluetooth spojení naráz, proto stejný senzor nepřipojujte přes Bluetooth k oběma programům.":
        "Trainers and straps usually allow only 1–2 Bluetooth connections at a time, so do not connect the same sensor to both apps over Bluetooth.",
    "jiný program": "another app",
    "Klikněte na „Přepnout na Bluetooth senzory“, AntFan vybere BT verze vašich senzorů.":
        "Click \"Switch to Bluetooth sensors\" and AntFan selects the BT versions of your sensors.",
    "V Nastavení → Senzory spusťte hledání a vyberte senzory s označením (BT).":
        "In Settings → Sensors, scan and select the sensors marked (BT).",
    "Běží {who}. V něm párujte senzory přes Bluetooth.": "{who} is running. Pair your sensors there over Bluetooth.",
    "Běží {who}. ANT+ dongle má AntFan, takže v {who} párujte senzory přes Bluetooth (ANT+ senzory, které umí obojí, vysílají i BT). {BT_LIMIT}\n\nKdyž chcete mít v obou programech ANT+, zapojte druhý dongle.":
        "{who} is running. AntFan has the ANT+ dongle, so pair your sensors in {who} over Bluetooth (dual ANT+/BT sensors broadcast BT too). {BT_LIMIT}\n\nTo use ANT+ in both apps, plug in a second dongle.",
    "Běží {who}. Máte dva ANT+ dongly, každý program má svůj.": "{who} is running. You have two ANT+ dongles, one for each app.",
    "Běží {who} a jsou zapojené dva ANT+ dongly. AntFan si vezme volný, {who} ten druhý. V obou programech párujte senzory přes ANT+, ANT+ senzor vysílá všem naráz. Na Bluetooth nic neměňte.":
        "{who} is running and two ANT+ dongles are plugged in. AntFan takes the free one, {who} the other. Pair sensors over ANT+ in both apps, an ANT+ sensor broadcasts to all at once. No Bluetooth changes needed.",
    "ANT+ dongle drží {who}. AntFan může jet přes Bluetooth.": "{who} holds the ANT+ dongle. AntFan can use Bluetooth.",
    "ANT+ dongle drží {who}. Nechte ho tam a AntFan připojte k senzorům přes Bluetooth. {how}\n\nV {who} pak párujte senzory jen přes ANT+, ať se o Bluetooth nepřetahujete. {BT_LIMIT}\n\nSpolehlivější je druhý ANT+ dongle: AntFan si vezme ten volný a vše zůstane na ANT+.":
        "{who} holds the ANT+ dongle. Leave it there and connect AntFan to the sensors over Bluetooth. {how}\n\nIn {who}, pair sensors over ANT+ only so the apps do not fight over Bluetooth. {BT_LIMIT}\n\nA second ANT+ dongle is more reliable: AntFan takes the free one and everything stays on ANT+.",
    "Běží {who} a AntFan čte senzory přes Bluetooth.": "{who} is running and AntFan reads sensors over Bluetooth.",
    "Běží {who} a AntFan je připojen k senzorům přes Bluetooth. {BT_LIMIT} Když {who} používá ANT+, je vše v pořádku. Pokud i {who} jede přes Bluetooth, připojte jeden z programů přes ANT+ (AntFan: vyberte senzory bez označení (BT)).":
        "{who} is running and AntFan is connected to the sensors over Bluetooth. {BT_LIMIT} If {who} uses ANT+, all is fine. If {who} also uses Bluetooth, connect one of the apps over ANT+ (AntFan: select sensors without the (BT) mark).",

    # --- config / profiles
    "Výchozí": "Default",
    "Zadejte jméno profilu.": "Enter a profile name.",
    "Poslední profil smazat nejde.": "The last profile cannot be deleted.",
    "Nový profil": "New profile",
    "Jméno nového profilu (zkopíruje se aktuální nastavení):": "New profile name (current settings are copied):",
    "Přejmenovat profil": "Rename profile",
    "Nové jméno profilu:": "New profile name:",
    "Profil: ": "Profile: ",
    "Smazat": "Delete",
    "Profil „{name}“ už existuje.": "Profile \"{name}\" already exists.",
    "Spravovat profily…": "Manage profiles…",
    "Profil": "Profile",
    "Nový": "New",
    "Přejmenovat": "Rename",
    "Smazat profil „{name}“?": "Delete profile \"{name}\"?",

    # --- controller
    "Chytře: výkon zvyšuje, tep drží": "Smart: power raises, HR holds",
    "Vyšší stupeň z výkonu a tepu": "Higher level of power and HR",
    "Vítr podle rychlosti jízdy": "Wind by ride speed",
    "čekám na data": "waiting for data",
    "tep drží stupeň": "HR holds level",
    "tep drží rychlost": "HR holds speed",
    "žádná data ze senzorů": "no sensor data",
    "chybí výkon": "no power",
    "chybí tep": "no HR",
    "chybí rychlost": "no speed",
    "chybí": "no ",
    "dofukování ještě {v}:{v2:02d}": "cooldown {v}:{v2:02d} left",
    "tep {hr_smoothed:.0f} bpm": "HR {hr_smoothed:.0f} bpm",
    "výkon {power_smoothed:.0f} W": "power {power_smoothed:.0f} W",
    "vítr {v:.0f} km/h": "wind {v:.0f} km/h",
    "minimum podle výkonu": "minimum by power",
    "minimum: {why}": "minimum: {why}",

    # --- drink
    "Teplota 0–45 °C.": "Temperature 0–45 °C.",
    "Interval 1–120 min.": "Interval 1–120 min.",
    "Napijte se · zhruba {ml} ml": "Drink · about {ml} ml",
    "Každých {v:.0f} min, zhruba {v2} ml ({v3:.0f} ml/h)": "Every {v:.0f} min, about {v2} ml ({v3:.0f} ml/h)",

    # --- fans
    "Zadejte IP adresu Shelly.": "Enter the Shelly IP address.",
    "Zadejte adresu Home Assistant, token a entitu.": "Enter the Home Assistant address, token and entity.",
    "Entita musí mít tvar fan.nazev nebo switch.nazev.": "The entity must look like fan.name or switch.name.",
    "Shelly má zapnuté heslo. AntFan zatím umí jen Shelly bez hesla.":
        "The Shelly has a password set. AntFan currently supports only Shelly without a password.",
    "Home Assistant odmítl token (401).": "Home Assistant rejected the token (401).",
    "Shelly vrátilo chybu {code}": "Shelly returned error {code}",
    "Shelly na {base} neodpovídá ({e})": "Shelly at {base} is not responding ({e})",
    "Home Assistant vrátil chybu {code}": "Home Assistant returned error {code}",
    "Home Assistant na {base} neodpovídá ({e})": "Home Assistant at {base} is not responding ({e})",
    "Home Assistant nezná entitu {entity}.": "Home Assistant does not know the entity {entity}.",

    # --- miio_fan
    "vrátil chybu": "returned error",
    "Token musí mít 32 hexadecimálních znaků (16 bajtů)": "The token must have 32 hex characters (16 bytes)",
    "Příliš krátká odpověď": "Response too short",
    "Neplatná odpověď (magic)": "Invalid response (magic)",
    "Token musí být 32 hexadecimálních znaků": "The token must be 32 hex characters",
    "Neplatný kontrolní součet – špatný token?": "Invalid checksum – wrong token?",
    "model {model} (starší protokol, neověřeno)": "model {model} (older protocol, untested)",
    "připojeno": "connected",
    "Ventilátor neodpověděl na příkaz (špatný token nebo nedostupný)": "The fan did not answer the command (wrong token or unreachable)",
    "Ventilátor vrátil chybu: {v}": "Fan returned error: {v}",
    "model {model} (podle specifikace MIoT, neověřeno)": "model {model} (from the MIoT spec, untested)",
    "model {v} neznám, používám ruční nastavení": "unknown model {v}, using manual settings",
    "Ventilátor odmítl nastavení {v}: kód {v2}": "The fan rejected setting {v}: code {v2}",
    "Ventilátor na {ip} neodpovídá (zkontrolujte IP a Wi-Fi)": "Fan at {ip} is not responding (check the IP and Wi-Fi)",
    "Síťová chyba: {e}": "Network error: {e}",
    "Nelze dešifrovat odpověď – špatný token?": "Cannot decrypt the response – wrong token?",
    "připojeno: {note}": "connected: {note}",
    "připojeno{v} (nepodporuje: ": "connected{v} (not supported: ",
    "pípání": "beeps",
    "podsvícení": "display light",

    # --- overlay
    "% max. tepu": "% max HR",
    "Tepová zóna": "HR zone",
    "Nic": "None",
    "dofukování": "cooldown",
    "dofukování ještě": "cooldown",
    "neměří se": "not measuring",
    "Ventilátor neodpovídá": "Fan not responding",
    "Velikost": "Size",
    "Druhé číslo": "Second value",
    "tep drží": "HR holds",
    "bez dat": "no data",
    "čeká na data": "waiting for data",
    "vítr": "wind",
    "ručně {v}": "manual {v}",
    "vítr {wind:.0f} km/h": "wind {wind:.0f} km/h",
    "Napijte se · {ml} ml": "Drink · {ml} ml",
    "Slabá baterie · ": "Low battery · ",
    "Napijte": "Drink",
    "Lišta navrchu": "Overlay bar",
    "Malý proužek přes Rouvy: stupeň ventilátoru, důvod a upozornění. Přetažením myší ho posunete, kliknutím na stupeň přepnete Auto, 1, 2… Vyp.":
        "A small strip on top of Rouvy: fan level, reason and alerts. Drag it to move, click the level to cycle Auto, 1, 2… Off.",
    "Zobrazit lištu": "Show bar",
    "Jen upozornění (jinak skrytá, při upozornění se na 20 s ukáže)": "Alerts only (hidden otherwise, shows for 20 s on an alert)",
    "Vrátit lištu do rohu": "Move bar back to corner",
    "zóna {z}": "zone {z}",
    "Výpadek příjmu · {power_gap_s:.0f} s": "Signal lost · {power_gap_s:.0f} s",

    # --- pairing
    "Zašlapejte (aspoň pár otáček) a navlhčete tepový pás nebo se ho dotkněte. Senzory, které zareagují, jsou vaše.":
        "Pedal (at least a few turns) and wet or touch your HR strap. The sensors that react are yours.",
    "jediný v dosahu (nereagoval)": "only one in range (did not react)",
    ", silný signál": ", strong signal",
    "pás začal měřit": "strap started measuring",
    "pás se probudil během hledání": "strap woke up during the scan",
    "výkon z 0 vyskočil": "power jumped from 0",
    "probudil se šlapáním": "woke up by pedaling",
    "Nenašel se žádný senzor. Zkontrolujte, že je ANT+ dongle zapojený (nebo zapnutý Bluetooth), pás nasazený a navlhčený a během hledání šlapejte, aby se powermetr probudil. Pak to zkuste znovu.":
        "No sensor found. Check that the ANT+ dongle is plugged in (or Bluetooth is on), the strap is on and wet, and pedal during the scan so the power meter wakes up. Then try again.",
    "Žádný senzor nezareagoval. Hned po spuštění zašlapejte aspoň pár otáček a navlhčete pás. Pokud jsou senzory spárované s Rouvy přes Bluetooth, nemusí se AntFanu ukázat.":
        "No sensor reacted. Right after starting, pedal a few turns and wet the strap. Sensors paired with Rouvy over Bluetooth may not show up in AntFan.",
    "objevil se až během hledání": "appeared during the scan",
    "nereaguje, nejspíš cizí": "not reacting, probably not yours",
    "blízko, ale nereaguje": "close, but not reacting",
    "Tepový pás nepoznám: v dosahu je víc pásů a žádný nezareagoval. Navlhčete elektrody, nasaďte pás a zkuste znovu, nebo ho vyberte ručně.":
        "Cannot tell which HR strap is yours: several are in range and none reacted. Wet the electrodes, put the strap on and try again, or select it manually.",
    "Tepový pás se nenašel: navlhčete elektrody a nasaďte ho, bez kontaktu nevysílá.":
        "No HR strap found: wet the electrodes and put it on, it does not broadcast without skin contact.",
    "Výkon nepoznám: v dosahu je víc powermetrů/trenažérů a žádný nezareagoval. Během hledání šlapejte, nebo vyberte senzor ručně.":
        "Cannot tell which power source is yours: several power meters/trainers are in range and none reacted. Pedal during the scan, or select the sensor manually.",
    "Powermetr ani trenažér se nenašel: zašlapejte, probouzí se pohybem.":
        "No power meter or trainer found: pedal, they wake up on movement.",
    "tep stoupl o {v} bpm": "HR rose by {v} bpm",

    # --- pairing_ui / souběh
    "Bluetooth verze vybraných senzorů nejsou vidět. Zapněte Bluetooth, odpojte senzory od Rouvy na Bluetooth a vyberte senzory (BT) ručně v Senzorech.":
        "The Bluetooth versions of the selected sensors are not visible. Turn Bluetooth on, disconnect the sensors from Rouvy on Bluetooth and select the (BT) sensors manually under Sensors.",
    "Souběh s Rouvy": "Riding with Rouvy",
    "Jak jet zároveň s Rouvy, Zwiftem, TrainerRoad nebo MyWhoosh. Jeden ANT+ dongle může mít jen jeden program.":
        "How to ride alongside Rouvy, Zwift, TrainerRoad or MyWhoosh. One ANT+ dongle can be used by only one app.",
    "Teď neběží žádná známá tréninková aplikace a dongle nikdo jiný nedrží.":
        "No known training app is running and no one else holds the dongle.",
    "Hledám Bluetooth verze senzorů…": "Looking for Bluetooth versions of the sensors…",
    "Vybráno: ": "Selected: ",
    "Zavřít": "Close",
    "Výběr uložen: ": "Selection saved: ",
    "Hledání se nepovedlo": "Scan failed",
    ". Bez Bluetooth verze zůstává: ": ". Staying without a Bluetooth version: ",
    "Hledám vaše senzory… {PAIR_SCAN_S} s": "Looking for your sensors… {PAIR_SCAN_S} s",
    "Hledám vaše senzory… {left} s": "Looking for your sensors… {left} s",
    "Vaše senzory": "Your sensors",
    "Vaše senzory se nepodařilo poznat": "Could not identify your sensors",
    "Více": "More",
    "Upozornit, když běží Rouvy a podobné aplikace": "Notify when Rouvy or similar apps are running",
    "Možnosti: (a) dva ANT+ dongly, každý program má svůj; (b) Rouvy na ANT+, AntFan na Bluetooth; (c) Rouvy na Bluetooth, AntFan na ANT+. ":
        "Options: (a) two ANT+ dongles, one per app; (b) Rouvy on ANT+, AntFan on Bluetooth; (c) Rouvy on Bluetooth, AntFan on ANT+. ",
    "Zrušit": "Cancel",
    "Nereagují, nejspíš patří sousedům: ": "Not reacting, probably the neighbors': ",
    "Přepnout na Bluetooth senzory": "Switch to Bluetooth sensors",
    "Zkusit znovu": "Try again",
    "Použít": "Apply",

    # --- qr
    "text je na QR kód příliš dlouhý": "text is too long for a QR code",

    # --- ride
    "Regenerace": "Recovery",
    "Vytrvalost": "Endurance",
    "Tempo": "Tempo",
    "Práh": "Threshold",
    "VO2max": "VO2max",
    "Anaerobní": "Anaerobic",
    "Sprint": "Sprint",
    "Maximum": "Maximum",
    "Nelze spočítat: chybí výkon nebo tep v obou polovinách jízdy.":
        "Cannot compute: power or HR is missing in one half of the ride.",
    "Pod 5 % je dobré: tep držel krok s výkonem.": "Below 5 % is good: HR kept pace with power.",
    " U intervalů má menší vypovídací hodnotu.": " Less meaningful for interval workouts.",
    "5–10 %: tep ke konci stoupal, možná únava, teplo nebo málo pití.":
        "5–10 %: HR drifted up toward the end, possibly fatigue, heat or too little drinking.",
    "Nad 10 %: tep v druhé polovině výrazně ujel, jízda byla nad aerobní kapacitou.":
        "Over 10 %: HR drifted a lot in the second half, the ride was beyond your aerobic capacity.",
    "O kolik % se ve 2. polovině jízdy zhoršil poměr výkon/tep proti 1. polovině. ":
        "How much the power/HR ratio worsened in the 2nd half of the ride vs. the 1st half. ",

    # --- ride_ui
    "Shrnutí jízdy": "Ride summary",
    "Stupně ventilátoru": "Fan levels",
    "Každá jízda delší než 5 minut se uloží jako CSV. Dvojklikem otevřete její shrnutí.":
        "Every ride longer than 5 minutes is saved as CSV. Double-click to open its summary.",
    "Délka": "Duration",
    "Ø výkon": "Avg power",
    "Max. výkon": "Max power",
    "Práce": "Work",
    "Ø kadence": "Avg cadence",
    "Ø tep": "Avg HR",
    "Posun tepu": "HR drift",
    "Čas v zónách výkonu": "Time in power zones",
    "Čas v zónách tepu": "Time in HR zones",
    "Začátek": "Start",
    "Zatím žádná uložená jízda.": "No saved rides yet.",
    "Jízdy jsou ve složce:\n{d}\n\n({e})": "Rides are in this folder:\n{d}\n\n({e})",
    "Otevřít složku": "Open folder",
    "Otevřít shrnutí": "Open summary",
    "Soubor {name} nejde načíst.": "Cannot load file {name}.",
    "{v} · FTP {ftp} W · max. tep {hr_max} bpm": "{v} · FTP {ftp} W · max HR {hr_max} bpm",
    "Stupeň {i}": "Level {i}",

    # --- usb_diag
    "ve Správci úloh (proces AntFan.exe nebo pythonw.exe)": "in Task Manager (process AntFan.exe or pythonw.exe)",
    "Dongle byl resetován.": "Dongle reset.",
    "ANT+ dongle je zapojený, ale nejde otevřít – drží ho jiný proces nebo je v zaseknutém stavu.":
        "The ANT+ dongle is plugged in but cannot be opened – another process holds it or it is stuck.",
    "v Monitoru činností (proces AntFan nebo Python)": "in Activity Monitor (process AntFan or Python)",
    "Monitor činností": "Activity Monitor",
    "Správce úloh": "Task Manager",
    "Běží programy, které dongle používají:": "Apps using the dongle are running:",
    "Jeden dongle může mít v jednu chvíli jen jeden program. AntFan ho druhému programu nebere, aby mu nerozbil spojení. Možnosti:":
        "One dongle can be used by only one app at a time. AntFan does not take it from the other app so as not to break its connection. Options:",
    "  1. Druhý ANT+ dongle – AntFan si sám vezme ten volný (nejspolehlivější).":
        "  1. A second ANT+ dongle – AntFan takes the free one by itself (most reliable).",
    "  2. Nechat dongle tomu programu a AntFan přepnout na Bluetooth senzory (pruh v okně jízdy nebo Nastavení → Souběh).":
        "  2. Leave the dongle to that app and switch AntFan to Bluetooth sensors (bar in the ride window or Settings → Other apps).",
    "  3. Spustit nejdřív AntFan a „Spustit měření“, až potom Rouvy/Zwift a v něm párovat senzory jen přes Bluetooth.":
        "  3. Start AntFan and press Start first, then Rouvy/Zwift, and pair sensors there over Bluetooth only.",
    "Žádný známý program, který by dongle držel, neběží. Zkuste:": "No known app holding the dongle is running. Try:",
    "  1. tlačítko „Reset donglu“,": "  1. the Reset dongle button,",
    "  2. vytáhnout dongle a zapojit ho do jiného USB portu (ne do hubu),":
        "  2. unplugging the dongle and plugging it into another USB port (not a hub),",
    "dongle ztracen": "dongle lost",
    "  4. Ukončit ten program – ": "  4. Quit that app – ",
    "  3. v Monitoru činností zkontrolovat, že neběží jiný program, který používá ANT+.":
        "  3. checking in Activity Monitor that no other app using ANT+ is running.",
    "  3. ve Správci zařízení ověřit, že dongle má ovladač libusbK.":
        "  3. checking in Device Manager that the dongle has the libusbK driver.",
    "USB reset tu nejde. Vytáhněte dongle a zapojte ho znovu.": "USB reset is not possible here. Unplug the dongle and plug it back in.",
    "zkontrolujte i ikonky v horní liště (Zwift Launcher a Garmin Express běží na pozadí i po zavření okna).":
        "check the menu bar icons too (Zwift Launcher and Garmin Express keep running after the window is closed).",
    "zkontrolujte i ikonky u hodin (Zwift Launcher a Garmin Express běží na pozadí i po zavření okna).":
        "check the tray icons too (Zwift Launcher and Garmin Express keep running after the window is closed).",
    "Běží i jiná instance AntFan (PID {v}).": "Another AntFan instance is running (PID {v}).",
    "Tento ovladač USB reset nepodporuje (WinUSB). Vytáhněte dongle a zapojte ho znovu.":
        "This driver does not support USB reset (WinUSB). Unplug the dongle and plug it back in.",

    # --- vitr_ui
    "Rychlost na 1. prahu": "Speed at 1st threshold",
    "Pokles nejvýš": "Max decrease",
    "Vítr: plná rychlost při": "Wind: full speed at",
    "Rychlost 0–100 %, pokles nad 0 %/s, vítr 10–120 km/h.": "Speed 0–100 %, decrease above 0 %/s, wind 10–120 km/h.",
    "Výstup": "Output",
    "Plynulá rychlost: od 1. do posledního prahu roste lineárně do 100 %. Vítr: pod 5 km/h vypnuto, rychlost jízdy posílá trenažér (FE-C), např. z Rouvy. Ventilátor bez rychlosti v % dostane nejbližší stupeň.":
        "Smooth speed: rises linearly to 100 % from the 1st to the last threshold. Wind: off below 5 km/h, ride speed comes from the trainer (FE-C), e.g. from Rouvy. A fan without % speed gets the nearest level.",
    "Stupně": "Levels",
    "Plynulá rychlost": "Smooth speed",
    "Vítr: minimum podle výkonu a tepu (pomalé stoupání do kopce)": "Wind: minimum by power and HR (slow climbs)",
    "bez rychlosti z trenažéru": "no speed from trainer",
    "ventilátor zatím na {act:.0f} %": "fan still at {act:.0f} %",
    "stupeň {lv}": "level {lv}",

    # --- web
    "Připojuji…": "Connecting…",
    "Obrazovku nechte rozsvícenou, jinak se obnovování zastaví.": "Keep the screen on, otherwise updates stop.",
    "Příkaz se nepodařilo odeslat.": "Could not send the command.",
    "Bez spojení s počítačem": "No connection to the computer",

    # --- xiaomi
    "Účet Xiaomi nevrátil přihlašovací údaje.": "The Xiaomi account returned no credentials.",
    "Zrušeno.": "Cancelled.",
    "Vypršel čas na naskenování QR kódu. Zkuste to znovu.": "Time to scan the QR code ran out. Try again.",
    "Nepodařilo se spojit s účtem Xiaomi ({e})": "Could not connect to the Xiaomi account ({e})",
    "Přihlášení se nepodařilo dokončit ({e})": "Could not complete sign-in ({e})",
    "Hledám zařízení na serveru {server}…": "Looking for devices on server {server}…",
    "Spojení s účtem Xiaomi spadlo ({e})": "Connection to the Xiaomi account dropped ({e})",
    "Účet Xiaomi": "Xiaomi account",
    "Připojuji se k účtu Xiaomi…": "Connecting to the Xiaomi account…",
    "Otevřít přihlášení v prohlížeči": "Open sign-in in browser",
    "Název": "Name",
    "Použít vybraný": "Use selected",
    "Přihlášeno. Načítám zařízení…": "Signed in. Loading devices…",
    "V aplikaci Mi Home klepněte na + (nebo Profil) → Skenovat a naskenujte kód. Pak přihlášení potvrďte v telefonu. Na tomto počítači můžete místo toho otevřít přihlášení v prohlížeči.":
        "In the Mi Home app tap + (or Profile) → Scan and scan the code. Then confirm the sign-in on your phone. On this computer you can open the sign-in in a browser instead.",
    "Na účtu se nenašlo žádné zařízení s tokenem.": "No device with a token was found on the account.",
    "Token z účtu Xiaomi": "Token from Xiaomi account",
    "Vyberte ventilátor a klikněte na Použít vybraný.": "Select a fan and click Use selected.",
    "Na účtu není žádný ventilátor. Vyberte zařízení ručně.": "There is no fan on the account. Select a device manually.",
    "Nečekaná chyba: {e}": "Unexpected error: {e}",
}
