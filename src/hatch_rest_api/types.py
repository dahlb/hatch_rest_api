from typing import TypedDict, Any


class SimpleSoundContent(TypedDict):
    """
    This is a partial type of only the fields used internally
    """
    id: int
    title: str
    wavUrl: str


class SoundContent(TypedDict):
    """
    No guarantees here, some display fields may be nullable.
    These types were inferred based off the free/included content
    from a Rest Gen2 (riot) device
    """

    id: int
    createDate: str
    updateDate: str
    title: str
    description: str
    hidden: bool
    newItem: bool
    displayOrder: int
    contentType: str
    category: str
    tier: str
    extent: str
    alarmOnly: bool
    author: "Any | None"
    narrator: "Any | None"
    duration: "Any | None"
    imageUrl: str
    mp3Url: "str | None"
    wavUrl: "str | None"
    color: Any
    series: "list[Any]"
    products: "list[str]"
    libraryVersion: int
    libraryVersionString: str
    url: str
    contentSeries: bool
    hatchId: int
    contentSource: str
    seriesSize: int
    tagIds: "list"
    altTagIds: "list"
    mixIds: "list"
    red: "Any | None"
    green: "Any | None"
    blue: "Any | None"
    white: "Any | None"
    sixCharacterColor: str
    rotateSeries: bool
    contentfulId: "Any | None"
    rotationType: str
    legacy: bool
    contentId: int
    contentful: bool
    personalized: bool
