from pydantic import BaseModel
from goldenverba.components.types import FileData
from typing import List, Optional

class QueryPayload(BaseModel):
    query: str
    course_id: str = None


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
    course_id: str = None




class QueryRequestWithGroundTruth(BaseModel):
    question: str
    answer: str
    ground_truth: str
    rubric: str
    default_rubric: str = """Correctness: If the answer correctly answers the question, below are the details for different scores:
            - Score 0: the answer is completely incorrect, doesn't mention anything about the question or is completely contrary to the correct answer.
                - For example, when asked “How to terminate a databricks cluster”, the answer is an empty string, or content that's completely irrelevant, or sorry I don't know the answer.
            - Score 1: the answer provides some relevance to the question and answers one aspect of the question correctly.
                - Example:
                    - Question: How to terminate a databricks cluster
                    - Answer: Databricks cluster is a cloud-based computing environment that allows users to process big data and run distributed data processing tasks efficiently.
                    - Or answer:  In the Databricks workspace, navigate to the "Clusters" tab. And then this is a hard question that I need to think more about it
            - Score 2: the answer mostly answers the question but is missing or hallucinating on one critical aspect.
                - Example:
                    - Question: How to terminate a databricks cluster”
                    - Answer: “In the Databricks workspace, navigate to the "Clusters" tab.
                    Find the cluster you want to terminate from the list of active clusters.
                    And then you'll find a button to terminate all clusters at once”
            - Score 3: the answer correctly answers the question and is not missing any major aspect. In this case, to score correctness 3, the final answer must be correct, final solution for numerical problems is of utmost importance.
                - Example:
                    - Question: How to terminate a databricks cluster
                    - Answer: In the Databricks workspace, navigate to the "Clusters" tab.
                    Find the cluster you want to terminate from the list of active clusters.
                    Click on the down-arrow next to the cluster name to open the cluster details.
                    Click on the "Terminate" button. A confirmation dialog will appear. Click "Terminate" again to confirm the action.”
            - Comprehensiveness: How comprehensive is the answer, does it fully answer all aspects of the question and provide comprehensive explanation and other necessary information. Below are the details for different scores:
            - Score 0: typically if the answer is completely incorrect, then the comprehensiveness is also zero.
            - Score 1: if the answer is correct but too short to fully answer the question, then we can give score 1 for comprehensiveness.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: First, you will need a Databricks access token with the appropriate permissions. You can generate this token through the Databricks UI under the 'User Settings' option. And then (the rest is missing)
            - Score 2: the answer is correct and roughly answers the main aspects of the question, but it's missing description about details. Or is completely missing details about one minor aspect.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: You will need a Databricks access token with the appropriate permissions. Then you'll need to set up the request URL, then you can make the HTTP Request. Then you can handle the request response.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: You will need a Databricks access token with the appropriate permissions. Then you'll need to set up the request URL, then you can make the HTTP Request. Then you can handle the request response.
            - Score 3: the answer is correct, and covers all the main aspects of the question
            - Readability: How readable is the answer, does it have redundant information or incomplete information that hurts the readability of the answer.
            - Score 0: the answer is completely unreadable, e.g. full of symbols that's hard to read; e.g. keeps repeating the words that it's very hard to understand the meaning of the paragraph. No meaningful information can be extracted from the answer.
            - Score 1: the answer is slightly readable, there are irrelevant symbols or repeated words, but it can roughly form a meaningful sentence that covers some aspects of the answer.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: You you  you  you  you  you  will need a Databricks access token with the appropriate permissions. And then then you'll need to set up the request URL, then you can make the HTTP Request. Then Then Then Then Then Then Then Then Then
            - Score 2: the answer is correct and mostly readable, but there is one obvious piece that's affecting the readability (mentioning of irrelevant pieces, repeated words)
                - Example:
                    - Question: How to terminate a databricks cluster
                    - Answer: In the Databricks workspace, navigate to the "Clusters" tab.
                    Find the cluster you want to terminate from the list of active clusters.
                    Click on the down-arrow next to the cluster name to open the cluster details.
                    Click on the "Terminate" button…………………………………..
                    A confirmation dialog will appear. Click "Terminate" again to confirm the action.
            - Score 3: the answer is correct and reader friendly, no obvious piece that affect readability.          
            The format in which you should provide results-
                Correctness:
                    -Score
                    -Explanation of score
                Readability:
                    -Score
                    -Explanation of score
                Comprehensiveness:
                    -Score
                    -Explanation of score"""
    course_id: str = None


class QueryRequestResume(BaseModel):
    query: list[str]
    course_id: str = None

class QueryRequestaqg(BaseModel):
    query: str
    NumberOfVariants: int
    course_id: str = None

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

class AuthDetails(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str

class Course(BaseModel):
    id: int
    fullname: str  # Updated field name to match the data

class RequestAGA(BaseModel):
    course_shortname : str
    assignment_name : str
    ground_truth: str = ""
    rubric: str


class TokenWithRoles(BaseModel):
    access_token: str
    token_type: str
    roles: Optional[List[str]] = None