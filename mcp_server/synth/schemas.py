"""One Pydantic row model per output table: the single source of truth for column names, order and types."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PSEUDO_ID = "Psuedo ID"  # sic — the workbook's spelling is the key in every table
TERMS = ("Autumn", "Spring", "Summer")

Flag = Annotated[int, Field(ge=0, le=1)]


class Row(BaseModel):
    """A row of one output table. Validate a DataFrame with ``TypeAdapter(list[Model])`` over ``to_dict("records")``."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @classmethod
    def columns(cls) -> list[str]:
        """Workbook column names in model field order."""
        return [field.alias or name for name, field in cls.model_fields.items()]


class CensusRow(Row):
    pseudo_id: str = Field(alias=PSEUDO_ID)
    gender: Literal["F", "M"] = Field(alias="Gender")
    ethnicity: str = Field(alias="Ethnicity") 
    language: str = Field(alias="Language")  
    fsm_eligible: Flag = Field(alias="FSMeligible")
    in_care_at_current_school: Flag = Field(alias="InCareAtCurrentSchool")
    academic_year: str = Field(alias="AcademicYear")  # _POC
    census_term: Literal["AUT", "SPR", "SUM"] = Field(alias="CensusTerm")  # _POC
    enrol_status: Literal["C", "S"] = Field(alias="EnrolStatus")  # _POC
    age_at_start_of_academic_year: int = Field(alias="AgeAtStartOfAcademicYear")  # _POC
    urn: str = Field(alias="URN")  # _POC


class DeprivationRow(Row):
    pseudo_id: str = Field(alias=PSEUDO_ID)
    home_area: str = Field(alias="HomeArea") 
    school_area: str = Field(alias="SchoolArea") 
    deprivation_score: float = Field(alias="DeprivationScore", ge=0, le=1)  
    deprivation_decile: int = Field(alias="DeprivationDecile", ge=1, le=10)  # rank within cohort, 10 = most deprived


class SchoolRow(Row):
    urn: str = Field(alias="URN")
    school_name: str = Field(alias="SchoolName")
    school_la: str = Field(alias="SchoolLA")


class DisplayNameRow(Row):
    pseudo_id: str = Field(alias=PSEUDO_ID)
    display_name: str = Field(alias="DisplayName")
    gender: Literal["F", "M"] = Field(alias="Gender")


TABLES: dict[str, type[Row]] = {
    "personal_data_school_census": CensusRow,
    "personal_data_deprivation": DeprivationRow,
    "schools": SchoolRow,
    "display_names": DisplayNameRow,
}
TABLE_COLUMNS: dict[str, list[str]] = {key: model.columns() for key, model in TABLES.items()}
PERSONAL_DATA_SCHOOL_CENSUS = CensusRow.columns()
PERSONAL_DATA_DEPRIVATION = DeprivationRow.columns()
SCHOOLS = SchoolRow.columns()
DISPLAY_NAMES = DisplayNameRow.columns()

SYNTHETIC_SCHOOL_NAMES = [
    "Ashfield Academy",
    "Brookmere High School",
    "Castleton School",
    "Dunmore Community College",
    "Elmwood Academy",
    "Fairhaven High School",
    "Greystone School",
    "Hollybrook Academy",
    "Ironbridge Community School",
    "Juniper Park Academy",
    "Kingsmead School",
    "Larkhill Academy",
]
SYNTHETIC_FIRST_NAMES = {
    "F": [
        "Aaliyah",
        "Amelia",
        "Ava",
        "Bea",
        "Cleo",
        "Esme",
        "Freya",
        "Grace",
        "Hana",
        "Iris",
        "Jess",
        "Lena",
        "Maya",
        "Mei",
        "Nadia",
        "Noor",
        "Olivia",
        "Priya",
        "Rosa",
        "Sasha",
        "Tia",
        "Yasmin",
        "Zara",
        "Zoe",
    ],
    "M": [
        "Ade",
        "Adam",
        "Cory",
        "Dylan",
        "Ethan",
        "Finlay",
        "Harvey",
        "Jordan",
        "Kai",
        "Leo",
        "Liam",
        "Mason",
        "Noah",
        "Omar",
        "Owen",
        "Ravi",
        "Reuben",
        "Riley",
        "Sol",
        "Theo",
        "Tomas",
        "Tyler",
        "Yusuf",
        "Zak",
    ],
}
SYNTHETIC_LAST_NAMES = [
    "Ahmed",
    "Begum",
    "Bennett",
    "Clarke",
    "Doyle",
    "Ellis",
    "Frost",
    "Hussain",
    "Khan",
    "Kowalski",
    "Lynch",
    "Marsh",
    "Mensah",
    "Nguyen",
    "Okafor",
    "Owusu",
    "Patel",
    "Reid",
    "Roberts",
    "Shah",
    "Singh",
    "Walsh",
    "Wright",
    "Young",
]
