from pydantic import BaseModel
from goldenverba.components.types import FileData


class QueryPayload(BaseModel):
    query: str


class ConversationItem(BaseModel):
    type: str
    content: str


class GeneratePayload(BaseModel):
    query: str
    context: str
    conversation: list[ConversationItem]


class SearchQueryPayload(BaseModel):
    query: str
    doc_type: str
    page: int
    pageSize: int


class GetDocumentPayload(BaseModel):
    document_id: str


class ResetPayload(BaseModel):
    resetMode: str


class LoadPayload(BaseModel):
    reader: str
    chunker: str
    embedder: str
    fileBytes: list[str]
    fileNames: list[str]
    filePath: str
    document_type: str
    chunkUnits: int
    chunkOverlap: int


class ImportPayload(BaseModel):
    data: list[FileData]
    textValues: list[str]
    config: dict

class QueryRequest(BaseModel):
    query: str

class QueryRequestaqg(BaseModel):
    query: str
    NumberOfVariants: int

class ConfigPayload(BaseModel):
    config: dict


class GetComponentPayload(BaseModel):
    component: str


class SetComponentPayload(BaseModel):
    component: str
    selected_component: str

class MoodleRequest(BaseModel):
    course_name: str
    assignment_name: str

class CourseIDRequest(BaseModel):
    course_shortname: str