import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("DRT_SECRET_KEY", "drt-system-secret-key-change-in-production")

    # Database priority: DATABASE_URL > DRT_DB_TYPE
    # Render/cloud sets DATABASE_URL automatically; local uses DRT_DB_TYPE
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    DB_TYPE = os.environ.get("DRT_DB_TYPE", "sqlite").lower()

    if DATABASE_URL:
        # Render provides postgres://... but SQLAlchemy needs postgresql://...
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    elif DB_TYPE == "mysql":
        MYSQL_HOST = os.environ.get("DRT_MYSQL_HOST", "localhost")
        MYSQL_PORT = int(os.environ.get("DRT_MYSQL_PORT", 3306))
        MYSQL_USER = os.environ.get("DRT_MYSQL_USER", "")
        MYSQL_PASSWORD = os.environ.get("DRT_MYSQL_PASSWORD", "")
        MYSQL_DB = os.environ.get("DRT_MYSQL_DB", "ai_drt_system")
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
        )
    elif DB_TYPE == "postgresql":
        PG_HOST = os.environ.get("DRT_PG_HOST", "localhost")
        PG_PORT = int(os.environ.get("DRT_PG_PORT", 5432))
        PG_USER = os.environ.get("DRT_PG_USER", "")
        PG_PASSWORD = os.environ.get("DRT_PG_PASSWORD", "")
        PG_DB = os.environ.get("DRT_PG_DB", "ai_drt_system")
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        )
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "drt_system.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours

    # Defect class options
    DEFECT_CLASSES = ["CND", "Equipment", "HARDWARE", "INTERCONNECT", "NPF", "OPERATOR_PROCESS", "ORDER", "R&R", "SOFTWARE", "TBD", "TEST"]

    # Defect class → value → definition mapping (from Excel)
    DEFECT_CLASS_VALUE_MAP = {
        "TEST": {
            "AUTOTEST_SERVER_DOWN": "Autotest/CPP server issue, self reboot, no communication",
            "COULD_NOT_CLASSIFY": "Test failure that can not be classified",
            "DEFECTIVE_TESTER_CABLE": "Tester cable defective, pinched, connector damaged",
            "DIAG_MISSING": "Diag image not available to boot (TFTP server, storage device)",
            "DOWNLOAD_BAD": "Fail to download/install software image",
            "EEPROM_MISPRGRMD": "EEPROM/IDPROM/PROM not programmed correctly",
            "EQUIPMENT_PROBLEM": "Test equipment issues (Traf. Gen, Terminal, Power, Chamber...)",
            "FIXTURE_PROBLEM": "Test Fixtures Issues (specially build Test Equipment, MTP, HI Pot, Load Cards...)",
            "GOLD_BOARD_FAILURE": "Gold Board issue",
            "HIPOT_BOX_ISSUE": "Failure caused by Hi Pot equipment/setup",
            "ICT_FAILURE": "ICT tester issue",
            "MACADDRESS": "Mac Address missing or wrong",
            "NETWORK_ISSUE": "Network related issues (autotest network down or slow)",
            "NO_BOOT": "UUT cannot boot to IOS/diag",
            "PACKET_DROPPED": "Packet lost during traffic test",
            "POWER_CYCLE_BOX_ISSUE": "Failure caused by power cycle equipment",
            "POWER_INTERRUPT": "Power interruption during test",
            "RETEST_NO_DEBUG": "Retest without any debug action to try to reproduce the failure",
            "REVISION_PROBLEM": "Incorrect Revision/Version",
            "ROHS_ISSUE": "Failure related to RoHS compliance",
            "SCRIPT_PROBLEM": "Test script related problem",
            "SLOT_FAILURE": "Chassis/SIP/Module or similar slot failure",
            "TST_ACCESSORIES_MALFUNCTION": "Test setup accessories failures (scanners, neoware, wise, thin client...)",
            "TST_DATA_PROPAGATION": "Data not propagated between servers in timely manner",
            "TST_SWITCH_ISSUE": "Test Switch issue",
            "TST-TERMINAL_SERVER_DOWN": "Terminal server issues",
            "WRONG_UUT_RECORDED": "Test script assign fail record to wrong SN",
        },
        "SOFTWARE": {
            "BAD_DIAG_IMAGE": "Bad/wrong Diag Image",
            "FIRMWARE_FAILURE": "Bad/wrong/missing Firmware",
            "IMAGE_CORRUPT": "Corrupted software image",
            "ROMMON_FAILURE": "Bad/wrong/missing Rommon",
            "SOFTWARE_BAD": "Bad/wrong SW caused no boot, functional issues",
            "SW_ERROR_INTERRUPT": "Software error once it booted, software glitch, reboot by itself",
        },
        "INTERCONNECT": {
            "BENT_LEAD": "Lead is bent",
            "BGA_MISSING_BALL": "Visual or x-ray evidence of BGA ball missing",
            "BGA_SHORT": "Visual or x-ray evidence of BGA solder short, bridging",
            "COMP_DAMAGED": "Component damaged during assembly or handling",
            "COMP_EXTRA": "Extra component installed during manufacturing process",
            "COMP_KNOCKED_OFF": "Component knocked off during manufacturing process",
            "COMP_LIFTED": "Component lifted from the fab pad",
            "COMP_MISALIGNED": "Component placed or positioned wrongly or badly",
            "COMP_MISSING": "Component missing, not installed during manufacturing process",
            "COMP_REVERSED": "Component installed in the opposite/wrong direction",
            "COMP_SHORT": "Component conductive surface shorting to adjacent components",
            "COMP_TOMBSTONE": "Component lifted tombstone during reflow soldering process",
            "COMP_TOUCHING": "Component touching adjacent component in nonconforming way",
            "COMP_UNDERNEATH": "Component underneath another component or part",
            "COMP_UPSIDE_DOWN": "Component installed upside down during manufacturing process",
            "COMP_WRONG": "Wrong/incorrect component installed during manufacturing process",
            "CONTAMINATION": "Product contamination during manufacturing process",
            "GOLDFINGER_DAMAGED": "Damage/contamination on gold fingers, gold pins or any gold surface contact area",
            "INCOMPLETE_REWORK": "Rework not completed properly, wrong or missing step",
            "JUMPER_WORKMANSHIP": "Jumper wire not installed properly",
            "LIFTED_PAD": "Separation between outer edge of conductor or land and laminate surface",
            "PCBA-FLASH_RESEAT": "Connection between flash device and PCBA not sufficient, reseat required",
            "PCBA-RESEATED_IC": "Connection between IC device and PCBA not sufficient, reseat/rework required",
            "PIN_NOT_THRU_CARD": "Component PIN tip not visible from other side of the board after wave process",
            "SOLDER_BALL": "Excess solder, spheres of solder that remain after the soldering process",
            "SOLDER_BRIDGE": "Excess solder, bridging across conductors that should not be joined",
            "SOLDER_COLD": "Cold/Rosin solder connection that exhibits poor wetting",
            "SOLDER_DEWETTING": "Molten solder coats a surface and then recedes to leave irregularly shaped mounds",
            "SOLDER_EXCESS": "Excess solder, solder splashes or tinning",
            "SOLDER_FRACTURED": "Fractured or cracked solder",
            "SOLDER_INSUFFICIENT": "Insufficient amount of solder applied",
            "SOLDER_MISSING": "Missing solder",
            "SOLDER_NONWETTING": "Inability of molten solder to form a metallic bond with the basis metal",
            "SOLDER_OPEN": "No connection between component termination and fab pad",
            "SOLDER_PASTE_ISSUE": "Issues with solder paste like short, insufficient",
            "SOLDER_SPLASH": "Excess solder, splashes on metal component surfaces",
            "SOLDER_TOUCHUP": "Nonconforming touch-up or rework of soldered connection",
            "SOLDER_WEBBING": "Excess solder, webbing",
            "VIPPO_DAMAGE": "Vippo Damage, Via In Pad Plated Over",
            "VOID": "Air bubble in solder joint",
            "WIREBOND_DAMAGE": "Wirebond failure related (Missing, Short, Broken, Lifted pad, etc.)",
        },
        "OPERATOR_PROCESS": {
            "ACCKIT_ISSUE": "Any issue with accessory kit (missing, wrong, incomplete...)",
            "BEZEL_ISSUE": "Issue with bezel (wrong, scratch, discoloration...)",
            "CABLE_LOOSE": "Product/UUT cable loose, not connected properly",
            "CABLE_MISSING": "Product/UUT cable not installed per BOM",
            "CHASSIS_WRONG": "Wrong Chassis used against the order",
            "COMP_MECHANICAL": "Mechanical part assembly issue (EMI gasket, carrier, filters...)",
            "CONTAM_OPTICAL_FIBER_CABLE": "Dirty Optical Surface (dust, oil deposit, contamination...)",
            "DAMAGED_CARD": "Physically damaged Card (dent, scratch, bent, guide pin...)",
            "DRAM_LOOSE": "DRAM/Memory not inserted properly or memory socket issue",
            "FLASH_ISSUE": "Issue with Flash memory/module/card/SSD (wrong, missing, extra...)",
            "FUNCTIONAL_AREACHECK": "Test failed for missing PASS record from required previous test step",
            "HARDWARE_DAMAGED": "Damaged chassis, backplane, components, bezel or any other hardware",
            "HEATSINK_ISSUE": "Issue with heatsink (missing, damaged, wrong, position...)",
            "INCORRECT_OPERATOR_RESPONSE": "Operator enter incorrect information or not respond in time allowed",
            "INSERTION_WRONG": "Card/module not inserted properly (seating issue, wrong slot...)",
            "INVALID_HW_CONFIGURATION": "Configuration issues (invalid quantity, part extra/missing, wrong location...)",
            "LABEL_ISSUE": "Label Related Failures (wrong SN, missing, cosmetic, misprinted...)",
            "LOOPBACK_ISSUE": "All loopback related problems (missing, wrong, damaged, dirty...)",
            "MEMORY_MISSING": "Memory missing (not installed in PCBA socket...)",
            "MEMORY_WRONG": "Memory wrong (wrong size, PN, vendor...)",
            "MISASSEMBLED": "General Category for all misassemble related issues",
            "MISSED_SCAN": "Operator scan incorrect barcodes on traveler or UUT",
            "PCBA_ISSUE": "PCBA related issue (wrong, missing, damaged...)",
            "REPAIR_DEVIATION": "Product is repaired per Deviation requirement",
            "REPAIR_ECO": "Product is repaired per ECO requirements",
            "SCREW_ISSUE": "Issue with screw (wrong, missing, loose, stripped...)",
            "SOFTWARE_WRONG": "Wrong software installed due to operator/process issue",
            "SWITCH_INCORRECTLY_SET": "Issue with the switches (Power, LED switch, ON/OFF...)",
            "TEST_CABLE_NOT_CONNECTED": "Test cable not connected properly before test start",
            "TEST_SETUP_ISSUE": "Any issue related to test equipment operator setup",
            "WORKMANSHIP": "Product not assembled per specs",
            "TEST_CALIBRATION_ISSUE": "Any calibration issues related to improper calibration technique",
            "EPOXY_ISSUE": "UV or Thermal Epoxy related failures",
            "FIBER DAMAGE_ISSUE": "Optical fiber of optical device related failures",
            "TIMPAD": "TIMpad removed and replaced (everything looks normal)",
            "TIMPAD_EXPIRED": "TIMpad expired replaced",
            "TIMPAD_CONTACT": "TIMpad poor/uneven contact",
            "ASSEMBLY_PROCESS": "HS re-assembled/re-tighten",
            "HS_LINER": "HS liner not removed before assembled",
        },
        "HARDWARE": {
            "BACKPLANE_FAILURE": "Any functional or mechanical failure on Backplane/Midplane",
            "BACKPLANE_PIN": "Backplane pin failure (functional, missing, bent, short, damaged...)",
            "BACKPLANE_SLOT": "Backplane slot failure (functional, undetected board, damaged...)",
            "BATTERY_FAILURE": "Battery failures, typically CC 35#",
            "CABLE_FAILURE": "Any Cable failure that belongs to HW/UUT",
            "CHASSIS_FAILURE": "Failures on chassis, backplane, midplane, bezel, interconnections",
            "COMP_BENT_PIN": "Bent pin on components (IC, capacitors, resistors, diodes...)",
            "COMP_BURNT": "Component burnt while UUT was powered up",
            "COMP_FAILURE_AMBIENT": "Component functional failure at ambient/room temperature",
            "COMP_FAILURE_COLD": "Component functional failure at cold temperature",
            "COMP_FAILURE_HEAT": "Component functional failure at hot temperature",
            "COMP_MISPROGRAMMED": "Component programmed incorrectly (PLD, PLA, FPGA...)",
            "COMP_NOT_PROGRAMMED": "Component not programmed (PLD, PLA, FPGA...)",
            "CONNECTOR_FAILURE": "Problem related to any type of Connectors (RJ45, USB, SMB...)",
            "COSMETIC_DEFECT": "Part has cosmetic defect (gouged, stains, tooling marks...)",
            "CPU_FAILURE": "CPU failures, typically Intel based pluggable CC 15#",
            "DISPLAY_FAILURE": "Issue with displays (LCD, LED, touchscreen, alphanumerical...)",
            "EEPROM_FAILURE": "Failures on EEPROM device (PCAMAP issue, miss programmed...)",
            "FAB_FAILURE": "Any functional or mechanical failure on FAB, typically class code 28#",
            "FAB_PAD_DAMAGED": "Fab pad damaged, lifted",
            "FAB_SHORT": "Fab short failure",
            "FAN_FAILED": "FAN or Fan Tray failures (wrong speed, not spinning, noise...)",
            "FLASH_FAILURE": "All Flash/NVRAM memory related problems",
            "FLASH_MISPRGMD": "Flash memory programmed incorrectly",
            "HDD_FAILURE": "Hard Drive failures, typically class code 58#",
            "LED_FAILED": "LED failures (not operational, wrong color, not lid...)",
            "MEMORY_FAILURE": "Memory functional failures (cannot detect, read/write issue...)",
            "OPTIC_MODULE_FAILURE": "Any problem related to Optic modules (XENPEK, XFP, SFP...)",
            "PCBA_FAILURE": "PCBA failure (functional, damaged, missing parts, contamination...)",
            "PIN_ISSUE": "All PIN related issues (modules, connectors, cards, backplanes...)",
            "PS_FAILURE": "Power Supply Module or Power Shelf failures",
            "SSD_FAILURE": "Solid State Drive failures, typically CC 16#",
            "TRACE_OPEN": "Fab trace open failure",
            "HS_PHYSICAL DAMAGE": "HS with physical damage (flatness, damaged, etc)",
            "HS_PART_ISSUE": "HS screw/washer defective/missing, etc",
            "HS_PERFORMANCE_SUSPECTED": "HS suspected to be cause of the failure",
        },
        # Classes with no predefined values - allow free input
        "CND": {},
        "Equipment": {},
        "NPF": {},
        "ORDER": {},
        "R&R": {},
        "TBD": {},
    }

    # Flat list of all defect values (for backward compatibility)
    DEFECT_VALUES = sorted(set(
        v for values in DEFECT_CLASS_VALUE_MAP.values() for v in values.keys()
    ))

    # BU options
    BU_OPTIONS = ["CRBU", "WNBU", "SRGBU", "UABU", "CSPBU"]
