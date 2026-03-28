import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("DRT_SECRET_KEY", "drt-system-secret-key-change-in-production")

    # Database: set DRT_DB_TYPE=mysql to use MySQL, otherwise defaults to SQLite
    DB_TYPE = os.environ.get("DRT_DB_TYPE", "sqlite").lower()

    if DB_TYPE == "mysql":
        MYSQL_HOST = os.environ.get("DRT_MYSQL_HOST", "localhost")
        MYSQL_PORT = int(os.environ.get("DRT_MYSQL_PORT", 3306))
        MYSQL_USER = os.environ.get("DRT_MYSQL_USER", "")
        MYSQL_PASSWORD = os.environ.get("DRT_MYSQL_PASSWORD", "")
        MYSQL_DB = os.environ.get("DRT_MYSQL_DB", "ai_drt_system")
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
        )
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "drt_system.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours

    # Defect class options
    DEFECT_CLASSES = ["CND", "Equipment", "Hardware", "NPF", "OPERATOR_PROCESS", "ORDER", "R&R", "TBD", "TEST"]

    # Defect value options
    DEFECT_VALUES = [
        "CABLE_LOOSE",
        "CHASSIS_FAILURE",
        "COULD_NOT_CLASSIFY",
        "EEPROM_MISPRGRMD",
        "EQUIPMENT_PROBLEM",
        "FIXTURE_PROBLEM",
        "Hardware",
        "INCORRECT_OPERATOR_RESPONSE",
        "MISASSEMBLED",
        "MISSED_SCAN",
        "NETWORK",
        "NO_BOOT",
        "OP_EJECTOR_CHECK",
        "OPERATOR_PROCESS",
        "ORDER",
        "PCBA_FAILRE",
        "PCBA_FAILURE",
        "SCRIPT_PROBLEM",
        "TEST_CABLE_NOT_CONNECTED",
        "TEST_DEBUG",
        "TEST_SCRIPTS",
        "TEST_SETUP_ISSUE",
    ]

    # BU options
    BU_OPTIONS = ["CRBU", "WNBU", "SRGBU", "UABU", "CSPBU"]
