from typing import Any, Literal, TypedDict

type JsonType = None | int | str | bool | list[JsonType] | dict[str, JsonType]

type Product = Literal[
    "rest",
    "riot",
    "riotPlus",
    "restPlus",
    "restMini",
    "restore",
    "restoreIot",
    "restoreV5",
    "alexa",
    "grow",
    "answeredReader",
]

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
    author: Any | None
    narrator: Any | None
    duration: Any | None
    imageUrl: str
    mp3Url: str | None
    wavUrl: str | None
    color: Any
    series: list[Any]
    products: list[str]
    libraryVersion: int
    libraryVersionString: str
    url: str
    contentSeries: bool
    hatchId: int
    contentSource: str
    seriesSize: int
    tagIds: list
    altTagIds: list
    mixIds: list
    red: Any | None
    green: Any | None
    blue: Any | None
    white: Any | None
    sixCharacterColor: str
    rotateSeries: bool
    contentfulId: Any | None
    rotationType: str
    legacy: bool
    contentId: int
    contentful: bool
    personalized: bool

type Gender = Literal['MALE', 'FEMALE']

class AwsIotCredentials(TypedDict):
    AccessKeyId: str
    Expiration: int
    SecretKey: str
    SessionToken: str

class AwsIotCredentialsResponse(TypedDict):
  Credentials: AwsIotCredentials
  IdentityId: str

class Baby(TypedDict):
    id: int
    createDate: str
    updateDate: str
    name: str
    birthDate: str | None
    dueDate: str | None
    birthWeight: int | None
    birthLength: int | None
    gender: Gender
    age: str
    stage: int
    lessThanTwoWeeksOld: bool

class Member(TypedDict):
    id: int
    createDate: str
    updateDate: str
    active: bool
    email: str
    babies: list[Baby]
    defaultUnitOfMeasure: Literal["imperial"] | str
    appType: Literal["iOS"] | str
    firstName: str
    lastName: str | None
    signupSource: Literal["rest"] | str
    timezone: str
    timeZoneAdjust: int
    stage: int

class LoginResponse(TypedDict):
    payload: Member
    sync: int
    token: str

class IotTokenResponse(TypedDict):
    endpoint: str
    identityId: str
    region: str
    cognitoPoolId: str
    token: str

class IotDeviceInfo(TypedDict):
    id: int
    createDate: str
    updateDate: str
    macAddress: str
    owner: bool
    name: str
    hardwareVersion: str
    product: Product
    thingName: str
    email: str
    memberId: int

type RestChargingStatus = Literal[0, 3, 5]

class RestIotRoutine(TypedDict):
    id: int
    macAddress: str
    name: str
    type: Literal["favorite", "sleep", "wake", "flex"]
    active: bool
    enabled: bool
    displayOrder: int
    sleepScene: bool
    followBySleepScene: bool
    button0: bool # true if this routine is available on touch ring
    startTime: None | str
    endTime: None | str
    daysOfWeek: Any | None
    steps: list[Any]

type IotSoundUntil = Literal["indefinite", "duration"] | str
